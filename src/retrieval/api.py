from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, cast

from src.er.canonical_index import CanonicalIndex
from src.er.fuzzy_match import FuzzySchoolMatcher
from src.graph.client import Edge, Node
from src.graph.kuzu_client import KuzuGraphClient
from src.retrieval.index import HybridIndex
from src.retrieval.level_filters import (
    GraphLevel,
    edge_types_for,
    is_node_visible_at_level,
    node_types_for,
)
from src.retrieval.ranking import rank_query_results

SourceTier = Literal["L1", "L2", "L3", "L4", "L5"]


@dataclass(frozen=True)
class QueryResult:
    """Per `api.md` FR-8.1 — every result carries `references` (NFR-4 ≥ 99%)."""

    node_id: str
    node_type: str
    properties: dict[str, Any]
    source_tier: SourceTier
    rank: str
    references: list[str]
    confidence: float
    t_valid_from: datetime | None
    t_valid_to: datetime | None
    path_explanation: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class CanonicalEntity:
    """Per `api.md` FR-8.2 — alias snap to L1 canonical."""

    canonical_id: str
    canonical_name: str
    type: str
    aliases: list[str]
    source_tier: SourceTier
    rank: str
    references: list[str]
    match_confidence: float


_TIER_ORDER: dict[str, int] = {"L1": 1, "L2": 2, "L3": 3, "L4": 4, "L5": 5}


class RetrievalService:
    """V1 retrieval service per FR-8.

    Two entry points:
      - `query_graph(...)` — substring + traversal lookup. p95 < 250ms (NFR-1).
      - `get_canonical_entity(alias, entity_type)` — alias snap. p95 < 50ms.

    Every result carries `references`; the implementation pulls them from
    edge `references` lists, satisfying NFR-4 (citation traceability ≥ 99%).
    """

    def __init__(
        self,
        graph: KuzuGraphClient,
        canonical_index: CanonicalIndex,
        matcher: FuzzySchoolMatcher | None = None,
        hybrid_index: HybridIndex | None = None,
    ) -> None:
        self._graph = graph
        self._index = canonical_index
        self._matcher = matcher or FuzzySchoolMatcher(canonical_index, threshold=85.0)
        self._hybrid_index = hybrid_index

    def query_graph(
        self,
        query: str,
        *,
        source_tier_min: SourceTier | None = None,
        time_range: tuple[datetime, datetime] | None = None,
        as_of: datetime | None = None,
        traversal_depth: int = 3,
        include_anomalies: bool = False,
        limit: int = 50,
    ) -> list[QueryResult]:
        """Substring-match query over node properties + outbound neighbor expansion.

        V1 uses property-text containment for the seed lookup; Pass 3+
        adds RRF (BM25 + HNSW) per ADR-002. The bitemporal `as_of` parameter
        filters edges (and any node attached only via filtered edges).
        """

        seeds = self._seed_lookup(
            query, limit=limit, source_tier_min=source_tier_min,
        )

        results: list[QueryResult] = []
        seen_ids: set[str] = {n.id for n in seeds}
        for seed in seeds:
            seed_refs = self._collect_node_references(seed)
            results.append(_node_to_query_result(
                seed, references=seed_refs, path=[],
            ))

        # Outbound expansion up to traversal_depth hops, capped at limit.
        frontier = list(seeds)
        for _depth in range(traversal_depth):
            next_frontier: list[Node] = []
            for n in frontier:
                if len(results) >= limit:
                    break
                neighbors = self._graph.neighbors(n.id, direction="out")
                for edge, target in neighbors:
                    if target.id in seen_ids:
                        continue
                    if not _edge_passes_filters(
                        edge,
                        source_tier_min=source_tier_min,
                        time_range=time_range,
                        as_of=as_of,
                        include_anomalies=include_anomalies,
                    ):
                        continue
                    seen_ids.add(target.id)
                    path = [{
                        "edge_type": edge.label,
                        "from": edge.from_id,
                        "to": edge.to_id,
                    }]
                    references = list(edge.references) or [edge.id]
                    results.append(_node_to_query_result(
                        target, references=references, path=path,
                    ))
                    next_frontier.append(target)
                    if len(results) >= limit:
                        break
            frontier = next_frontier

        # ADR-021: order by the tier-as-prior calibrated score (w_tier x w_rank
        # x HALO decay x credibility x RA-RAG consistency) — NOT a tier-first
        # pre-sort, so a fresh corroborated L5 claim can outrank a stale L1 one.
        return rank_query_results(results, now=datetime.now(tz=UTC))[:limit]

    # ------------------------------------------------------------------
    # V1.5b — multi-level retrieval (ADR-012)
    # ------------------------------------------------------------------

    def query_graph_structural(
        self,
        query: str,
        *,
        time_range: tuple[datetime, datetime] | None = None,
        as_of: datetime | None = None,
        traversal_depth: int = 2,
        limit: int = 50,
    ) -> list[QueryResult]:
        """Level A — deterministic structural subgraph (Pass-1 only).

        Returns User / Post / Comment / Thread / Subreddit nodes + Pass-1
        edges (AUTHORED / REPLIED_TO / BELONGS_TO_THREAD / POSTED_IN_FORUM
        / UPVOTED). No LLM-derived properties. Per ADR-012.
        """

        return self._query_at_level(
            "A", query,
            time_range=time_range, as_of=as_of,
            traversal_depth=traversal_depth, limit=limit,
            include_anomalies=False, source_tier_min=None,
        )

    def query_graph_clusters(
        self,
        query: str,
        *,
        time_range: tuple[datetime, datetime] | None = None,
        as_of: datetime | None = None,
        limit: int = 200,
    ) -> list[QueryResult]:
        """Level B — Topic + Cluster nodes + IN_CLUSTER edges.

        Per ADR-012: the cluster-review HITL flow consumes this. Posts and
        comments are NOT returned as primary results — only their
        membership weights via the Cluster nodes.
        """

        return self._query_at_level(
            "B", query,
            time_range=time_range, as_of=as_of,
            traversal_depth=1, limit=limit,
            include_anomalies=False, source_tier_min=None,
        )

    def query_graph_analyzed(
        self,
        query: str,
        *,
        source_tier_min: SourceTier | None = None,
        time_range: tuple[datetime, datetime] | None = None,
        as_of: datetime | None = None,
        traversal_depth: int = 3,
        include_anomalies: bool = False,
        limit: int = 50,
    ) -> list[QueryResult]:
        """Level C — full analyzed graph. Aliased to V1's `query_graph` per
        ADR-012. V1 callers can transparently switch from `query_graph` to
        `query_graph_analyzed` (and back) — semantics are identical."""

        return self.query_graph(
            query,
            source_tier_min=source_tier_min,
            time_range=time_range,
            as_of=as_of,
            traversal_depth=traversal_depth,
            include_anomalies=include_anomalies,
            limit=limit,
        )

    def query_graph_crosslinks(
        self,
        *,
        source_tier_min: SourceTier | None = None,
        time_range: tuple[datetime, datetime] | None = None,
        as_of: datetime | None = None,
        limit: int = 50,
    ) -> list[QueryResult]:
        """SAME_AS edges only (V1.5a cross-graph link surface).

        Used by per-team dashboards (V1.5c) to drill from a forum mention to
        its DB anchor. Returns both endpoints + the SAME_AS edge as the
        path explanation.
        """

        results: list[QueryResult] = []
        for edge_label, edge_endpoint_pairs in self._all_edges_of_type(
            "SAME_AS",
        ).items():
            for edge, source, target in edge_endpoint_pairs:
                if not _edge_passes_filters(
                    edge,
                    source_tier_min=source_tier_min,
                    time_range=time_range, as_of=as_of,
                    include_anomalies=False,
                ):
                    continue
                refs = list(edge.references) or [edge.id]
                results.append(_node_to_query_result(
                    source, references=refs, path=[],
                ))
                results.append(_node_to_query_result(
                    target, references=refs, path=[{
                        "edge_type": edge_label,
                        "from": edge.from_id, "to": edge.to_id,
                    }],
                ))
                if len(results) >= limit:
                    return results[:limit]
        return results[:limit]

    # ------------------------------------------------------------------
    # Level-typed query internals
    # ------------------------------------------------------------------

    def _query_at_level(
        self,
        level: GraphLevel,
        query: str,
        *,
        source_tier_min: SourceTier | None,
        time_range: tuple[datetime, datetime] | None,
        as_of: datetime | None,
        traversal_depth: int,
        limit: int,
        include_anomalies: bool,
    ) -> list[QueryResult]:
        """Run a level-filtered query. Identical shape to `query_graph`
        but only nodes + edges in the level's visibility set are surfaced.
        """

        seeds = self._seed_lookup(
            query, limit=limit, source_tier_min=source_tier_min,
            allowed_labels=node_types_for(level),
        )
        seeds = [n for n in seeds if is_node_visible_at_level(n.label, level)]
        allowed_edges = edge_types_for(level)

        results: list[QueryResult] = []
        seen_ids: set[str] = {n.id for n in seeds}
        for seed in seeds:
            seed_refs = self._collect_node_references(seed)
            results.append(_node_to_query_result(
                seed, references=seed_refs, path=[],
            ))

        frontier = list(seeds)
        for _depth in range(traversal_depth):
            next_frontier: list[Node] = []
            for n in frontier:
                if len(results) >= limit:
                    break
                neighbors = self._graph.neighbors(n.id, direction="out")
                for edge, target in neighbors:
                    if edge.label not in allowed_edges:
                        continue
                    if target.id in seen_ids:
                        continue
                    if not is_node_visible_at_level(target.label, level):
                        continue
                    if not _edge_passes_filters(
                        edge,
                        source_tier_min=source_tier_min,
                        time_range=time_range, as_of=as_of,
                        include_anomalies=include_anomalies,
                    ):
                        continue
                    seen_ids.add(target.id)
                    path = [{
                        "edge_type": edge.label,
                        "from": edge.from_id, "to": edge.to_id,
                    }]
                    references = list(edge.references) or [edge.id]
                    results.append(_node_to_query_result(
                        target, references=references, path=path,
                    ))
                    next_frontier.append(target)
                    if len(results) >= limit:
                        break
            frontier = next_frontier

        return results[:limit]

    def _all_edges_of_type(
        self, edge_label: str,
    ) -> dict[str, list[tuple[Edge, Node, Node]]]:
        """Return all edges of a given label + their endpoints.

        Used by `query_graph_crosslinks` for SAME_AS scan. V1.5a graphs
        are small enough that a full scan is fine; V1.6 may add an index.
        """

        out: list[tuple[Edge, Node, Node]] = []
        try:
            edges = list(self._graph.edges_of_type(edge_label))
        except AttributeError:
            edges = []
        for edge in edges:
            source = self._graph.get_node(edge.from_id)
            target = self._graph.get_node(edge.to_id)
            if source is None or target is None:
                continue
            out.append((edge, source, target))
        return {edge_label: out}

    def get_canonical_entity(
        self, alias: str, entity_type: Literal["School", "Program", "Specialty"],
    ) -> CanonicalEntity | None:
        """Alias snap per FR-8.2 + FR-3."""

        _ = entity_type  # V1: only School is canonicalized; entity_type held for API parity
        match = self._matcher.match(alias)
        if match is None:
            return None
        aliases = self._index.aliases_for(match.canonical_id)
        if match.matched_alias not in aliases:
            aliases.append(match.matched_alias)
        return CanonicalEntity(
            canonical_id=match.canonical_id,
            canonical_name=match.canonical_name,
            type=entity_type,
            aliases=aliases,
            source_tier="L1",
            rank="preferred",
            references=[match.canonical_id],
            match_confidence=match.score / 100.0,
        )

    def _seed_lookup(
        self,
        query: str,
        *,
        limit: int,
        source_tier_min: SourceTier | None,
        allowed_labels: frozenset[str] | None = None,
    ) -> list[Node]:
        """V1 seed: RRF (TF-IDF + cosine kNN) when a `HybridIndex` is wired,
        else case-insensitive substring scan over the live graph."""

        normalized = (query or "").strip().lower()
        if not normalized:
            return []

        if self._hybrid_index is not None:
            return [
                hit.node for hit in self._hybrid_index.search(
                    query, top_k=limit, source_tier_min=source_tier_min,
                )
            ]

        # Push the substring filter into Kùzu: a LIMIT on the bare scan reads only
        # the first rows in storage order (on the full 4.35M-node graph those are
        # empty-props corpus Posts -> zero hits, always). With the predicate
        # below, LIMIT caps *matches* while the engine scans the whole table.
        # `allowed_labels` keeps level-filtered seeds (e.g. Level B = Cluster/
        # Topic) from being crowded out of the cap by 1.37M Post matches.
        label_clause = ""
        params: dict[str, Any] = {"q": normalized, "cap": int(limit) * 20}
        if allowed_labels:
            label_clause = "AND list_contains($labels, n.label) "
            params["labels"] = sorted(allowed_labels)
        result = self._graph._conn.execute(
            "MATCH (n:Node) "
            "WHERE (lower(n.id) CONTAINS $q "
            "   OR lower(coalesce(n.properties_json, '')) CONTAINS $q) "
            + label_clause +
            "RETURN n.id, n.label, n.source_tier, n.properties_json LIMIT $cap",
            parameters=params,
        )
        scan = result[-1] if isinstance(result, list) else result
        hits: list[Node] = []
        while scan.has_next():
            row = cast("list[Any]", scan.get_next())
            node_id = str(row[0])
            label = str(row[1])
            tier = str(row[2])
            props_raw = row[3] or "{}"
            if not _tier_passes(tier, source_tier_min):
                continue
            hits.append(Node(
                id=node_id, label=label,
                source_tier=tier,  # type: ignore[arg-type]
                properties=json.loads(props_raw),
            ))
            if len(hits) >= limit:
                break
        return hits

    def _collect_node_references(self, node: Node) -> list[str]:
        """A node has no `references` field; we surface the node-id itself + any
        ingest-provenance property as a back-pointer for NFR-4 traceability."""

        refs: list[str] = [node.id]
        dump_ref = node.properties.get("source_dump_id")
        if isinstance(dump_ref, str) and dump_ref:
            refs.append(dump_ref)
        return refs


def _node_to_query_result(
    node: Node, *, references: list[str], path: list[dict[str, str]],
) -> QueryResult:
    return QueryResult(
        node_id=node.id,
        node_type=node.label,
        properties=node.properties,
        source_tier=node.source_tier,
        rank=str(node.properties.get("rank", "normal")),
        references=references,
        confidence=float(node.properties.get("confidence", 1.0)),
        t_valid_from=_parse_dt(node.properties.get("t_valid_from")),
        t_valid_to=_parse_dt(node.properties.get("t_valid_to")),
        path_explanation=path,
    )


def _edge_passes_filters(  # noqa: PLR0911 — each filter rule is an independent early return
    edge: Edge,
    *,
    source_tier_min: SourceTier | None,
    time_range: tuple[datetime, datetime] | None,
    as_of: datetime | None,
    include_anomalies: bool,
) -> bool:
    if not _tier_passes(edge.source_tier, source_tier_min):
        return False
    if not include_anomalies and (edge.qualifiers or {}).get("status") == "anomaly":
        return False
    if as_of is not None:
        if edge.t_ingest_from is not None and edge.t_ingest_from > as_of:
            return False
        if edge.t_ingest_to is not None and edge.t_ingest_to <= as_of:
            return False
    if time_range is not None and edge.t_valid_from is not None:
        lo, hi = time_range
        if edge.t_valid_from > hi:
            return False
        if edge.t_valid_to is not None and edge.t_valid_to < lo:
            return False
    return True


def _tier_passes(tier: str, source_tier_min: SourceTier | None) -> bool:
    if source_tier_min is None:
        return True
    return _TIER_ORDER.get(tier, 99) <= _TIER_ORDER.get(source_tier_min, 0)


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None
