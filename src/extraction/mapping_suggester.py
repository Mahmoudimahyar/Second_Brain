"""V1.5a Phase 3 — `MappingSuggester` (FR-1.5a-3).

Reads a `SchemaSnapshot` from a `DataSource` and proposes per-table mapping
verdicts: `node_type` (with name + properties), `edge_type` (when the table
is a join/bridge), or `skip` (no plausible mapping).

Heuristics (FR-1.5a-3.3):
  (a) embed each column-name + sample-value snippet via BGE-small
  (b) cosine-similarity against an internal node-property dictionary
  (c) tables with > 50% non-null FKs → edge candidate
  (d) tables with all-pk-only composite-PK structure → edge candidate
  (e) tables with sample values matching canonical entity aliases → bind
      to existing node type

Confidence ∈ [0, 1]:
  ≥ 0.90 → routing='auto'
  0.75 ≤ x < 0.90 → routing='hitl'
  < 0.75 → routing='reject' / skip

No LLM call. BGE embeddings only. Property-tested by mocking
`src.gateway.api.default_gateway` and asserting it's never invoked.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from rapidfuzz import fuzz

from src.embeddings.api import Embedding, EmbeddingService
from src.ingestion.sources.base import ColumnSpec, SchemaSnapshot, TableSpec

# ----------------------------------------------------------------------
# Pydantic outputs
# ----------------------------------------------------------------------


MappingType = Literal["node", "edge", "skip"]
Routing = Literal["auto", "hitl", "reject"]


class TableMappingProposal(BaseModel):
    """Per-table verdict (per data.md §Pydantic models)."""

    model_config = ConfigDict(extra="forbid")

    table_or_label: str
    mapping_type: MappingType
    target_type: str | None = None
    target_properties: dict[str, str] = Field(default_factory=dict)
    edge_endpoints: tuple[str, str] | None = None
    confidence: float
    reasoning_chain: list[str] = Field(default_factory=list)
    routing: Routing


class MappingProposal(BaseModel):
    """A suggester run's full output for one schema snapshot."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    per_table: list[TableMappingProposal] = Field(default_factory=list)
    overall_confidence: float = 0.0


# ----------------------------------------------------------------------
# Node-property dictionary (NPD)
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class NodePropertyDef:
    """One row of the canonical-node-property dictionary.

    Each row says: "an entity of type `node_type` is likely to have a column
    matching `property` (semantically described by `description`)."
    """

    node_type: str
    property: str
    description: str
    aliases: tuple[str, ...] = ()

    def text(self) -> str:
        """Text used for embedding — concatenation of property + description."""
        parts = [self.property, self.description, *self.aliases]
        return " | ".join(parts)


# Operational-table names that we always skip regardless of column shape.
SKIP_TABLE_NAMES: frozenset[str] = frozenset({
    "audit_log", "audit", "system_settings", "settings", "migrations",
    "schema_migrations", "alembic_version", "django_migrations", "users_session",
    "sessions", "cache", "celery_taskmeta", "celery_tasksetmeta",
    "django_admin_log", "django_content_type", "django_session",
    "django_site", "auth_permission", "auth_group",
})


def seed_node_property_dictionary() -> list[NodePropertyDef]:
    """Seed the NPD from V1's `docs/07-data/data-dictionary.md` node taxonomy.

    Hand-picked rows covering the core V1 node types. Extended as new types
    accrue from V1.5+ corpora. Kept compact (< ~50 rows) so per-table cosine
    scoring is fast.
    """

    npd: list[NodePropertyDef] = [
        # School
        NodePropertyDef("School", "name", "Canonical school name",
                        ("school name", "institution", "dental school name")),
        NodePropertyDef("School", "city", "City the school is in",
                        ("school city", "campus city")),
        NodePropertyDef("School", "state", "State / region the school is in",
                        ("school state", "region")),
        NodePropertyDef("School", "founding_year", "Year the school was founded",
                        ("school founded", "established", "year founded")),
        NodePropertyDef("School", "school_id", "Unique school identifier",
                        ("school id", "school_pk")),
        # Program (residency / specialty)
        NodePropertyDef("Program", "program_id", "Program identifier",
                        ("program_id", "residency_id", "specialty_id")),
        NodePropertyDef("Program", "name", "Program / specialty name",
                        ("program name", "specialty", "residency name")),
        NodePropertyDef("Program", "specialty", "Specialty type",
                        ("specialty type", "program type")),
        NodePropertyDef("Program", "school_id", "Which school offers the program",
                        ("offering school", "host institution")),
        # Metric (numeric per-school per-year)
        NodePropertyDef("Metric", "metric_name", "Name of the metric",
                        ("metric", "kpi", "measure")),
        NodePropertyDef("Metric", "metric_value", "Numeric value of the metric",
                        ("value", "amount", "kpi value")),
        NodePropertyDef("Metric", "cycle_year", "Application cycle year",
                        ("year", "cycle", "academic year")),
        NodePropertyDef("Metric", "unit", "Unit of the measurement",
                        ("currency", "metric unit")),
        # CycleYear
        NodePropertyDef("CycleYear", "cycle_year", "Application cycle (YYYY-YY)",
                        ("cycle", "academic year", "admissions cycle")),
        # User
        NodePropertyDef("User", "user_id", "Stable user identifier",
                        ("user id", "author id", "username id")),
        NodePropertyDef("User", "username", "User display name / handle",
                        ("user", "author", "handle", "screen name")),
        NodePropertyDef("User", "karma", "Reddit-style karma / reputation",
                        ("score", "reputation")),
        NodePropertyDef("User", "first_seen_utc", "When the user was first seen",
                        ("created at", "joined")),
        # Post
        NodePropertyDef("Post", "post_id", "Post identifier",
                        ("post id", "thread starter id")),
        NodePropertyDef("Post", "title", "Post title",
                        ("subject", "headline")),
        NodePropertyDef("Post", "body", "Post body text",
                        ("content", "selftext", "post content")),
        NodePropertyDef("Post", "created_utc", "When the post was created",
                        ("posted at", "created")),
        NodePropertyDef("Post", "score", "Post upvote score",
                        ("upvotes", "post score")),
        NodePropertyDef("Post", "author", "Author username",
                        ("posted by", "user")),
        NodePropertyDef("Post", "subreddit", "Subreddit / forum container",
                        ("forum", "sub", "category")),
        # Comment
        NodePropertyDef("Comment", "comment_id", "Comment identifier",
                        ("reply id", "comment_pk")),
        NodePropertyDef("Comment", "body", "Comment body text",
                        ("comment content", "reply text")),
        NodePropertyDef("Comment", "parent_id", "Parent comment or post",
                        ("reply to", "in_reply_to")),
        # Thread
        NodePropertyDef("Thread", "thread_id", "Thread identifier",
                        ("thread_id", "discussion_id")),
        NodePropertyDef("Thread", "title", "Thread title",
                        ("thread title", "discussion subject")),
        NodePropertyDef("Thread", "category", "Forum category",
                        ("subforum", "thread category", "forum category")),
        # Subreddit
        NodePropertyDef("Subreddit", "subreddit_id", "Subreddit identifier",
                        ("subreddit_id", "forum_id", "category_id")),
        NodePropertyDef("Subreddit", "name", "Subreddit name",
                        ("subreddit name", "sub", "forum name", "category name")),
        # Topic
        NodePropertyDef("Topic", "topic_id", "Topic identifier",
                        ("topic_id", "theme_id")),
        NodePropertyDef("Topic", "name", "Topic / theme name",
                        ("topic name", "theme name", "subject")),
        # Document (L2)
        NodePropertyDef("L2Document", "document_id", "Document identifier",
                        ("document_id", "page_id", "article_id")),
        NodePropertyDef("L2Document", "title", "Document title",
                        ("page title", "article title", "doc title")),
        NodePropertyDef("L2Document", "url", "Document source URL",
                        ("link", "source url", "permalink")),
        NodePropertyDef("L2Document", "body", "Document body / content",
                        ("article body", "page content", "text", "content")),
        NodePropertyDef(
            "L2Document", "published_utc", "When the document was published",
            ("published", "publish date", "published_at"),
        ),
        # Alias
        NodePropertyDef("Alias", "alias_text", "Alternative string for a canonical entity",
                        ("alias", "alternate name", "synonym")),
        NodePropertyDef("Alias", "canonical_id", "Canonical entity id this alias maps to",
                        ("canonical reference", "maps to")),
    ]
    return npd


# ----------------------------------------------------------------------
# The suggester
# ----------------------------------------------------------------------


_NODE_TYPE_PRIORS: dict[str, str] = {
    # Table-name → preferred node type heuristic (per FR-1.5a-3.3(e)).
    "school": "School",
    "schools": "School",
    "institution": "School",
    "institutions": "School",
    "user": "User",
    "users": "User",
    "post": "Post",
    "posts": "Post",
    "comment": "Comment",
    "comments": "Comment",
    "thread": "Thread",
    "threads": "Thread",
    "topic": "Topic",
    "topics": "Topic",
    "subreddit": "Subreddit",
    "subreddits": "Subreddit",
    "category": "Subreddit",  # SDN category ≈ subreddit
    "categories": "Subreddit",
    "metric": "Metric",
    "metrics": "Metric",
    "school_year_metrics": "Metric",
    "school_year_metric": "Metric",
    "program": "Program",
    "programs": "Program",
    "alias": "Alias",
    "aliases": "Alias",
    "document": "L2Document",
    "documents": "L2Document",
    "page": "L2Document",
    "pages": "L2Document",
}


@dataclass
class MappingSuggester:
    """Embedding-based suggester. Stateful: remembers prior-decision boosts."""

    embedding_service: EmbeddingService
    npd: list[NodePropertyDef] = field(default_factory=seed_node_property_dictionary)

    # Confidence thresholds (matched to V1 alias-resolution per FR-1.5a-3.4).
    auto_threshold: float = 0.90
    hitl_threshold: float = 0.75

    # Sample-row value limit per column (FR-1.5a-3.3a "first 5 distinct values").
    sample_value_limit: int = 5

    # Prior-decision memory for FR-1.5a-3.6.
    _prior_decisions: list[tuple[str, str, str]] = field(default_factory=list)
    _npd_embeddings: dict[str, Embedding] | None = field(default=None, init=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def suggest(self, snapshot: SchemaSnapshot) -> MappingProposal:
        proposals: list[TableMappingProposal] = []
        for table in snapshot.tables:
            proposals.append(self._suggest_table(table))
        overall = (
            sum(p.confidence for p in proposals) / max(len(proposals), 1)
        )
        return MappingProposal(
            source_id=snapshot.source_id,
            per_table=proposals,
            overall_confidence=overall,
        )

    def record_committed_decision(
        self,
        *,
        source_id: str,
        table_or_label: str,
        mapping_type: MappingType,
        target_type: str | None,
    ) -> None:
        """FR-1.5a-3.6 — store a finalized decision so similar tables in
        future snapshots get a confidence boost.
        """

        if target_type is None:
            return
        self._prior_decisions.append((source_id, table_or_label, target_type))

    # ------------------------------------------------------------------
    # Per-table dispatch
    # ------------------------------------------------------------------

    def _suggest_table(self, table: TableSpec) -> TableMappingProposal:
        chain: list[str] = []
        table_norm = table.name.lower().strip()

        # (e) operational tables → skip
        if table_norm in SKIP_TABLE_NAMES:
            chain.append(f"table name {table_norm!r} matches operational skip set")
            return TableMappingProposal(
                table_or_label=table.name,
                mapping_type="skip",
                target_type=None,
                confidence=0.99,
                reasoning_chain=chain,
                routing="reject",
            )

        # (c) + (d) edge-candidate heuristic
        edge_result = self._maybe_edge(table)
        if edge_result is not None:
            return edge_result

        # Default: node candidate. Combine heuristics + embedding similarity.
        return self._propose_node(table, chain)

    # ------------------------------------------------------------------
    # Edge detection (FR-1.5a-3.3(c) + (d))
    # ------------------------------------------------------------------

    def _maybe_edge(
        self, table: TableSpec,
    ) -> TableMappingProposal | None:
        n_cols = len(table.column_specs)
        n_fks = len(table.foreign_keys)
        pk_cols = set(table.primary_key or [])
        fk_cols = {c for fk in table.foreign_keys for c in fk.columns}

        # Classic join table: PK is composite AND every PK col is also an FK
        # AND at least 2 FKs.
        is_join_table = (
            len(pk_cols) >= 2
            and n_fks >= 2
            and pk_cols.issubset(fk_cols)
        )
        # Heavier-FK heuristic: > 50% of cols are FK-bound.
        is_heavy_fk = (
            n_fks >= 2 and n_cols > 0
            and (n_fks / n_cols) >= 0.5
        )
        if not (is_join_table or is_heavy_fk):
            return None

        if n_fks < 2:
            return None
        # Build the edge proposal.
        ref_tables = [fk.references_table for fk in table.foreign_keys]
        # Two-table edge case — most common.
        if len(ref_tables) == 2:
            endpoints: tuple[str, str] = (ref_tables[0], ref_tables[1])
        else:
            # > 2 FKs: pair the first two; further hops are V1.6.
            endpoints = (ref_tables[0], ref_tables[1])
        edge_name = _edge_name_for(table.name, endpoints)
        confidence = 0.91 if is_join_table else 0.82
        routing: Routing = "auto" if confidence >= self.auto_threshold else "hitl"
        return TableMappingProposal(
            table_or_label=table.name,
            mapping_type="edge",
            target_type=edge_name,
            edge_endpoints=endpoints,
            confidence=confidence,
            reasoning_chain=[
                (
                    f"PK={sorted(pk_cols)} FKs={[fk.columns for fk in table.foreign_keys]}"
                    f" → "
                    f"{'composite-PK join table' if is_join_table else 'heavy-FK bridge'}"
                ),
                f"derived edge name {edge_name}",
            ],
            routing=routing,
        )

    # ------------------------------------------------------------------
    # Node proposal (embedding-based)
    # ------------------------------------------------------------------

    def _propose_node(
        self, table: TableSpec, chain: list[str],
    ) -> TableMappingProposal:
        # Table-name prior
        table_norm = table.name.lower().strip()
        prior_node = _NODE_TYPE_PRIORS.get(table_norm)

        # Best-match scoring via NPD cosine similarity per column
        scored: dict[str, list[tuple[str, float]]] = {}
        for col in table.column_specs:
            best = self._best_match_for_column(col)
            if best is None:
                continue
            node_type, score = best
            scored.setdefault(node_type, []).append((col.name, score))

        # Sum per-node-type matched column scores.
        per_type_total: dict[str, float] = {
            nt: sum(s for _, s in pairs) for nt, pairs in scored.items()
        }
        if not per_type_total:
            # No NPD matches. If we have a strong prior from the table name
            # (e.g., "schools" → School), use it with low-but-not-zero conf.
            if prior_node is not None:
                chain.append(f"no NPD matches; using table-name prior → {prior_node}")
                return TableMappingProposal(
                    table_or_label=table.name,
                    mapping_type="node",
                    target_type=prior_node,
                    target_properties={},
                    confidence=0.80,
                    reasoning_chain=chain,
                    routing="hitl",
                )
            chain.append("no NPD matches; routing reject")
            return TableMappingProposal(
                table_or_label=table.name,
                mapping_type="skip",
                target_type=None,
                confidence=0.0,
                reasoning_chain=chain,
                routing="reject",
            )

        # Pick the node type with highest total score — BUT if there's a
        # strong table-name prior that also got at least one column match,
        # honor the prior. This handles the common case where ambiguous
        # generic columns (`id`, `name`) would otherwise route to the wrong
        # node type (e.g., `subreddits.{id,name}` going to School because
        # School also claims `name`).
        target_type = max(per_type_total, key=per_type_total.get)  # type: ignore[arg-type]
        if prior_node is not None and prior_node in per_type_total:
            # Override if the per-type difference isn't decisive.
            top_score = per_type_total[target_type]
            prior_score = per_type_total[prior_node]
            if prior_score >= 0.5 * top_score:
                target_type = prior_node
                chain.append(
                    f"table-name prior {prior_node!r} overrides scoring tie "
                    f"(prior {prior_score:.2f} vs top {top_score:.2f})",
                )

        # Normalize confidence by the number of matched columns, capped at 1.
        matched_cols = scored[target_type]
        # Top-K cosine average — stable across NPD growth.
        top_cos = sorted((s for _, s in matched_cols), reverse=True)[:5]
        avg_cos = sum(top_cos) / len(top_cos) if top_cos else 0.0
        column_coverage = min(len(matched_cols) / max(len(table.column_specs), 1), 1.0)
        base_confidence = 0.5 * avg_cos + 0.5 * column_coverage

        # Table-name prior boost. A clear table-name prior + strong column
        # signals = high-confidence auto. The two combined are nearly
        # always unambiguous in practice.
        if prior_node == target_type:
            if avg_cos >= 0.85 and len(matched_cols) >= 2:
                base_confidence = max(base_confidence, 0.92)
                chain.append(
                    f"strong table-name prior ({table_norm!r}→{target_type}) "
                    f"+ {len(matched_cols)} solid column matches → auto-tier",
                )
            else:
                base_confidence = max(base_confidence, 0.85)
                chain.append(
                    f"table name {table_norm!r} matches target {target_type}; "
                    f"boosting confidence",
                )
        # Prior-decision boost (FR-1.5a-3.6)
        if any(
            tn == table_norm and tt == target_type
            for _, tn, tt in self._prior_decisions
        ):
            base_confidence = min(1.0, base_confidence + 0.05)
            chain.append("prior committed decision on same table shape; +0.05")

        confidence = min(1.0, max(0.0, base_confidence))
        routing = _route(confidence, self.auto_threshold, self.hitl_threshold)

        # Property mapping (column_name → property_name) for matched columns.
        prop_map: dict[str, str] = {}
        for col_name, _score in matched_cols:
            prop_map[col_name] = col_name  # default identity; tunable in V1.5b UI

        chain.append(
            f"matched {len(matched_cols)} cols to {target_type} "
            f"avg_cos={avg_cos:.3f} coverage={column_coverage:.2f}",
        )

        return TableMappingProposal(
            table_or_label=table.name,
            mapping_type="node",
            target_type=target_type,
            target_properties=prop_map,
            confidence=confidence,
            reasoning_chain=chain,
            routing=routing,
        )

    # ------------------------------------------------------------------
    # Embedding helpers
    # ------------------------------------------------------------------

    def _best_match_for_column(
        self, col: ColumnSpec,
    ) -> tuple[str, float] | None:
        """Best (node_type, score) match for a column. Combines two signals:

        1. Lexical match (rapidfuzz token_set_ratio on column name vs NPD
           property + aliases). Deterministic, fast, handles exact/near-exact
           naming. Dominant signal for tables with conventional column names.
        2. Embedding cosine sim on the column text vs NPD def text. Provides
           semantic fallback (e.g., "tuition_amount" → Metric.metric_value).

        We return the highest score across both signals, mapped to the
        node type with the strongest evidence.
        """

        # Lexical signal
        lex_best_score = 0.0
        lex_best_node: str | None = None
        col_name_lower = col.name.lower().strip()
        for npd_def in self.npd:
            for candidate in (npd_def.property, *npd_def.aliases):
                cand_norm = candidate.lower().replace(" ", "_").strip()
                ratio = fuzz.token_set_ratio(col_name_lower, cand_norm) / 100.0
                if ratio > lex_best_score:
                    lex_best_score = ratio
                    lex_best_node = npd_def.node_type

        # Embedding signal (lower weight unless lexical is weak)
        col_text = self._column_text(col)
        col_emb = self.embedding_service.embed(col_text)
        npd_embs = self._ensure_npd_embeddings()
        emb_best_score = -1.0
        emb_best_node: str | None = None
        for npd_def in self.npd:
            npd_emb = npd_embs[npd_def.text()]
            score = _cosine(col_emb, npd_emb)
            if score > emb_best_score:
                emb_best_score = score
                emb_best_node = npd_def.node_type

        # Combine: lexical match ≥ 0.85 dominates; otherwise blend.
        if lex_best_score >= 0.85 and lex_best_node is not None:
            return lex_best_node, lex_best_score
        if emb_best_score >= 0.50 and emb_best_node is not None:
            # Lexical-weighted blend if both contribute.
            blended = 0.6 * emb_best_score + 0.4 * lex_best_score
            return emb_best_node, blended
        if lex_best_score >= 0.60 and lex_best_node is not None:
            return lex_best_node, lex_best_score * 0.7  # lower-confidence
        return None

    def _column_text(self, col: ColumnSpec) -> str:
        sample_snippet = " ".join(
            str(v) for v in (col.sample_values or [])[: self.sample_value_limit]
        )
        return f"{col.name} {col.type} {sample_snippet}".strip()

    def _ensure_npd_embeddings(self) -> dict[str, Embedding]:
        if self._npd_embeddings is None:
            texts = [d.text() for d in self.npd]
            batch = self.embedding_service.embed_batch(texts)
            self._npd_embeddings = {t: emb for t, emb in zip(texts, batch, strict=True)}
        return self._npd_embeddings


# ----------------------------------------------------------------------
# Module helpers
# ----------------------------------------------------------------------


def _cosine(a: Embedding, b: Embedding) -> float:
    if len(a.vector) != len(b.vector):
        return 0.0
    dot = sum(x * y for x, y in zip(a.vector, b.vector, strict=True))
    na = math.sqrt(sum(x * x for x in a.vector))
    nb = math.sqrt(sum(x * x for x in b.vector))
    if na == 0 or nb == 0:
        return 0.0
    return float(dot / (na * nb))


def _route(confidence: float, auto: float, hitl: float) -> Routing:
    if confidence >= auto:
        return "auto"
    if confidence >= hitl:
        return "hitl"
    return "reject"


def _edge_name_for(table_name: str, endpoints: Sequence[str]) -> str:
    """Derive an edge label from a join-table name + endpoints.

    Strategy: if the table name suggests an action (`enrollments`,
    `mentions`), uppercase the singular form. Otherwise concatenate
    endpoint names with `_HAS_`.
    """

    norm = table_name.lower().strip()
    action = norm[:-1].upper() if norm.endswith("s") else norm.upper()
    if action in {"USER", "SCHOOL", "POST"}:
        # Avoid name collisions with node types
        action = f"{endpoints[0].upper()}_HAS_{endpoints[1].upper()}"
    return action


__all__ = [
    "MappingProposal",
    "MappingSuggester",
    "NodePropertyDef",
    "TableMappingProposal",
    "seed_node_property_dictionary",
]
