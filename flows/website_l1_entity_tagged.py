"""V1.6a — L1 entity-tagged flow per ADR-020.

Local-only (no LLM, no external API). Reuses V1's `Pass1MentionExtractor`
+ `CanonicalIndex` to tag crawled pages with `Entity` mentions, plus
512-token / 64-token-overlap chunking matching V1 Pass 3 conventions.

Per FR-1.6a-4.2:
- For each CrawledRecord: chunk the body, write `Chunk` nodes + `HAS_CHUNK`
  edges (Page -> Chunk).
- For each mention extracted from the body: write a MENTIONS edge from
  the Page to the canonical Entity. The Entity node is a thin wrapper
  with the canonical_id as the node id (V1 L1 anchors already exist in
  the graph; this flow just connects the new Page to them).
- Auto-link threshold per V1 + V1.6a spec: score >= 95 -> auto-linked
  (MENTIONS.rank='preferred'); 75 <= score < 95 -> auto-linked but with
  needs_review=True flag + optional HITL enqueue.

Idempotency contract (FR-1.6a-4.4):
- Per-page tracking: re-running L1 on a page whose content_hash is
  unchanged is a no-op (we re-derive the same MENTIONS edges + same
  Chunk node IDs, all of which are upserts).

The chunking is a deliberately simple whitespace tokenizer — the V1
Pass 3 BGE-small embedding pipeline does its own SentencePiece-aware
chunking in production. For L1's "entity tagging" purpose plain
whitespace splits are sufficient + much faster.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from src.er.canonical_index import CanonicalIndex
from src.extraction.pass1_mention_extractor import Mention, Pass1MentionExtractor
from src.graph.client import Edge, Node, SourceTier
from src.graph.web_node_types import (
    HAS_CHUNK,
    MENTIONS,
    PAGE_LABEL,
    page_node_id,
)
from src.ingestion.adapters.crawl4ai_web import CrawledRecord
from src.ingestion.sources.website_crawl import CrawlDomainRow

# Chunk parameters per FR-1.6a-4.2 + V1 Pass 3 conventions.
CHUNK_TOKEN_WINDOW: int = 512
CHUNK_TOKEN_OVERLAP: int = 64
CHUNK_LABEL: str = "Chunk"
ENTITY_LABEL: str = "Entity"


# ---------------------------------------------------------------------------
# Optional HITL queue surface
# ---------------------------------------------------------------------------


class HITLEnqueuer(Protocol):
    def enqueue(self, *, item_type: str, payload: dict[str, Any]) -> str: ...


# ---------------------------------------------------------------------------
# Graph protocol — narrow surface
# ---------------------------------------------------------------------------


class GraphWriter(Protocol):
    def upsert_node(self, node: Node) -> None: ...

    def upsert_edge(self, edge: Edge) -> None: ...

    def get_node(self, node_id: str) -> Node | None: ...

    def nodes_of_label(
        self, label: str, *, limit: int = 10_000,
    ) -> list[Node]: ...


# ---------------------------------------------------------------------------
# Run-summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class L1RunSummary:
    job_id: str
    domain_id: str
    pages_processed: int
    chunks_written: int
    mentions_written: int
    auto_linked: int
    hitl_enqueued: int


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_l1_for_domain(
    *,
    domain: CrawlDomainRow,
    records: list[CrawledRecord],
    graph: GraphWriter,
    canonical: CanonicalIndex,
    job_id: str,
    hitl: HITLEnqueuer | None = None,
    now: datetime | None = None,
) -> L1RunSummary:
    """Run L1 entity-tagging + chunking for a domain's crawled records.

    `canonical` is a V1 `CanonicalIndex` loaded from the same SQLite that
    holds the L1 anchors; the Pass-1 mention extractor uses it to resolve
    aliases. `hitl` is optional — when provided, ambiguous mentions
    (score in [75, 95)) are also enqueued with item_type
    'entity_link_ambiguous'.
    """

    now = now or datetime.now(UTC)
    extractor = Pass1MentionExtractor(canonical)

    pages_processed = 0
    chunks_written = 0
    mentions_written = 0
    auto_linked = 0
    hitl_enqueued = 0
    # Entity ids already checked against the graph this run. The stub is
    # written ONLY when no node exists at canonical_id: KuzuClient.upsert_node
    # is a full overwrite (MERGE ... SET label/properties_json), so an
    # unconditional stub would clobber real V1 L1 anchors (School/Institution
    # nodes) with `label="Entity", properties={canonical_name}`.
    _stub_checked: set[str] = set()

    for record in records:
        from_page_id = page_node_id(
            url=record.url, content_hash=record.content_hash,
        )
        pages_processed += 1

        # ---- Chunking -----------------------------------------------
        chunks = _chunk_text(
            record.body_md,
            window=CHUNK_TOKEN_WINDOW,
            overlap=CHUNK_TOKEN_OVERLAP,
        )
        for chunk_idx, chunk_text in enumerate(chunks):
            chunk_id = _chunk_node_id(
                page_id=from_page_id, ordinal=chunk_idx,
                content=chunk_text,
            )
            graph.upsert_node(Node(
                id=chunk_id, label=CHUNK_LABEL, source_tier=domain.tier,
                properties={
                    "page_id": from_page_id,
                    "ordinal": chunk_idx,
                    "text": chunk_text,
                    "token_count": len(chunk_text.split()),
                    "content_hash": _sha256_16(chunk_text),
                    "t_valid_from": now.isoformat(),
                    "t_valid_to": None,
                    "t_ingest_from": now.isoformat(),
                    "t_ingest_to": None,
                },
            ))
            chunks_written += 1
            graph.upsert_edge(_make_has_chunk_edge(
                page_id=from_page_id, chunk_id=chunk_id,
                source_tier=domain.tier, valid_from=now,
            ))

        # ---- Entity tagging on the WHOLE body (extractor handles
        #      large bodies fine; chunk-level tagging happens in L2). --
        mentions = extractor.extract(record.body_md)
        for mention in mentions:
            ent_id = mention.canonical_id  # the V1 L1 anchor's node id
            if ent_id not in _stub_checked:
                _stub_checked.add(ent_id)
                if graph.get_node(ent_id) is None:
                    graph.upsert_node(_make_entity_stub(
                        canonical_id=ent_id,
                        canonical_name=mention.canonical_name,
                        source_tier=domain.tier,
                    ))
            graph.upsert_edge(_make_mentions_edge(
                page_id=from_page_id,
                entity_id=ent_id,
                mention=mention,
                source_tier=domain.tier,
                valid_from=now,
            ))
            mentions_written += 1
            if mention.needs_review:
                if hitl is not None:
                    hitl.enqueue(
                        item_type="entity_link_ambiguous",
                        payload={
                            "page_id": from_page_id,
                            "url": record.url,
                            "mention": mention.matched_alias,
                            "canonical_id": mention.canonical_id,
                            "score": mention.score,
                        },
                    )
                    hitl_enqueued += 1
            else:
                auto_linked += 1

    return L1RunSummary(
        job_id=job_id,
        domain_id=domain.domain_id,
        pages_processed=pages_processed,
        chunks_written=chunks_written,
        mentions_written=mentions_written,
        auto_linked=auto_linked,
        hitl_enqueued=hitl_enqueued,
    )


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def _chunk_text(
    text: str, *, window: int, overlap: int,
) -> list[str]:
    """Whitespace token chunker with overlap.

    Returns at least one chunk for non-empty text. Empty / whitespace-only
    text returns no chunks (no node written).
    """

    if not text or not text.strip():
        return []
    tokens = text.split()
    if len(tokens) <= window:
        return [text]
    stride = max(1, window - overlap)
    out: list[str] = []
    for start in range(0, len(tokens), stride):
        end = start + window
        chunk = " ".join(tokens[start:end])
        out.append(chunk)
        if end >= len(tokens):
            break
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256_16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _chunk_node_id(*, page_id: str, ordinal: int, content: str) -> str:
    """Content-hashed chunk id so re-running on same content yields same id."""

    return f"chunk:{_sha256_16(f'{page_id}|{ordinal}|{content}')}"


def _make_has_chunk_edge(
    *,
    page_id: str,
    chunk_id: str,
    source_tier: SourceTier,
    valid_from: datetime,
) -> Edge:
    return Edge(
        id=f"edge:has_chunk:{page_id}->{chunk_id}",
        label=HAS_CHUNK,
        from_id=page_id,
        to_id=chunk_id,
        source_tier=source_tier,
        rank="normal",
        references=[page_id, chunk_id],
        t_valid_from=valid_from,
        t_ingest_from=valid_from,
    )


def _make_entity_stub(
    *,
    canonical_id: str,
    canonical_name: str,
    source_tier: SourceTier,
) -> Node:
    """Entity stub for canonical ids with NO existing graph node.

    MUST only be written after `graph.get_node(canonical_id)` returned
    None (enforced in `run_l1_for_domain`): `KuzuClient.upsert_node` is
    a full overwrite, so writing this stub over an existing V1 L1 anchor
    (School/Institution) would destroy its label + properties.
    """

    return Node(
        id=canonical_id,
        label=ENTITY_LABEL,
        source_tier=source_tier,
        properties={
            "canonical_name": canonical_name,
        },
    )


def _make_mentions_edge(
    *,
    page_id: str,
    entity_id: str,
    mention: Mention,
    source_tier: SourceTier,
    valid_from: datetime,
) -> Edge:
    return Edge(
        id=f"edge:mentions:{page_id}->{entity_id}",
        label=MENTIONS,
        from_id=page_id,
        to_id=entity_id,
        source_tier=source_tier,
        rank="preferred" if not mention.needs_review else "normal",
        references=[page_id, entity_id],
        qualifiers={
            "matched_alias": mention.matched_alias,
            "score": mention.score,
            "needs_review": mention.needs_review,
        },
        confidence=mention.score / 100.0,
        t_valid_from=valid_from,
        t_ingest_from=valid_from,
    )


__all__ = [
    "CHUNK_LABEL",
    "CHUNK_TOKEN_OVERLAP",
    "CHUNK_TOKEN_WINDOW",
    "ENTITY_LABEL",
    "GraphWriter",
    "HITLEnqueuer",
    "L1RunSummary",
    "run_l1_for_domain",
]


# Silence unused-import warning — PAGE_LABEL is part of the module
# contract (re-exported for callers that need the label constant).
_ = PAGE_LABEL
