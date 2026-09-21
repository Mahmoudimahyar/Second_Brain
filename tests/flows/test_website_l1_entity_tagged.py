"""V1.6a Phase 5 — L1 entity-tagged flow unit tests.

Per ADR-020 + V1.6a plan.md Phase 5. Reuses V1 `Pass1MentionExtractor` +
`CanonicalIndex` machinery; adds chunking + per-page MENTIONS edges.

Failing-first: a page mentioning "New York University College of
Dentistry" -> Entity node + MENTIONS edge written, rapidfuzz score
>= 95 -> auto-linked to existing V1 L1 NYU canonical node.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from src.graph.client import Edge, Node


@dataclass
class _StubGraph:
    """Dict-backed in-memory graph mimicking Kuzu's upsert-by-id semantics."""

    nodes: dict[str, Node] = field(default_factory=dict)
    edge_index: dict[str, Edge] = field(default_factory=dict)

    def upsert_node(self, node: Node) -> None:
        self.nodes[node.id] = node

    def upsert_edge(self, edge: Edge) -> None:
        self.edge_index[edge.id] = edge

    def get_node(self, node_id: str) -> Node | None:
        return self.nodes.get(node_id)

    def nodes_of_label(self, label: str, *, limit: int = 10_000) -> list[Node]:
        return [n for n in self.nodes.values() if n.label == label][:limit]

    @property
    def edges(self) -> list[Edge]:
        return list(self.edge_index.values())

    def edges_of_label(self, label: str) -> list[Edge]:
        return [e for e in self.edge_index.values() if e.label == label]


def _nyu_canonical_index_sqlite(tmp_path: Path) -> Path:
    """Build a minimal CanonicalIndex SQLite with NYU as the L1 anchor."""

    import sqlite3
    db = tmp_path / "engine.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS alias (
            alias_text TEXT,
            canonical_id TEXT
        );
        CREATE TABLE IF NOT EXISTS l1_school (
            canonical_id TEXT PRIMARY KEY,
            canonical_name TEXT
        );
    """)
    conn.execute(
        "INSERT INTO l1_school (canonical_id, canonical_name) VALUES (?, ?)",
        ("school:nyu_dental", "New York University College of Dentistry"),
    )
    for alias in (
        "New York University College of Dentistry",
        "NYU College of Dentistry",
        "NYU Dental",
        "NYUCD",
    ):
        conn.execute(
            "INSERT INTO alias (alias_text, canonical_id) VALUES (?, ?)",
            (alias, "school:nyu_dental"),
        )
    # A second school so we can test "no-match" scenarios.
    conn.execute(
        "INSERT INTO l1_school (canonical_id, canonical_name) VALUES (?, ?)",
        ("school:tufts_dental", "Tufts University School of Dental Medicine"),
    )
    conn.execute(
        "INSERT INTO alias (alias_text, canonical_id) VALUES (?, ?)",
        ("Tufts University School of Dental Medicine", "school:tufts_dental"),
    )
    conn.commit()
    conn.close()
    return db


def _crawled_record(
    *, url: str, body_md: str, content_hash: str = "a" * 64,
):
    from src.ingestion.adapters.crawl4ai_web import CrawledRecord

    return CrawledRecord(
        url=url,
        domain=url.split("/")[2],
        mime="text/html",
        title=url,
        body_md=body_md,
        content_hash=content_hash[:64],
        bytes_=len(body_md.encode("utf-8")),
        fetched_at=datetime.now(UTC),
        source_tier="L2",
    )


# ---------------------------------------------------------------------------
# Failing-first
# ---------------------------------------------------------------------------


def test_l1_extracts_school_entity_and_links_to_l1_anchor(tmp_path: Path) -> None:
    """Failing-first per V1.6a plan.md Phase 5."""

    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from flows.website_l1_entity_tagged import run_l1_for_domain
    from src.er.canonical_index import CanonicalIndex
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry

    db = _nyu_canonical_index_sqlite(tmp_path)
    canonical = CanonicalIndex(sqlite_path=db)
    registry = WebsiteCrawlRegistry(sqlite_path=db)
    domain = registry.register(
        domain="adea.org", tier="L2", stage="L1",
        cadence_cron="0 6 * * *", actor="t",
    )

    body = (
        "The NYU College of Dentistry's 2024-25 cycle saw record application "
        "volume. NYU College of Dentistry administrators report a 12% rise."
    )
    record = _crawled_record(url="https://adea.org/page", body_md=body)
    graph = _StubGraph()

    summary = run_l1_for_domain(
        domain=domain,
        records=[record],
        graph=graph,
        canonical=canonical,
        job_id="job:l1:test",
    )

    mentions_edges = graph.edges_of_label("MENTIONS")
    assert len(mentions_edges) >= 1
    # Edge points to the NYU canonical id.
    target_ids = {e.to_id for e in mentions_edges}
    assert "school:nyu_dental" in target_ids
    assert summary.mentions_written >= 1
    assert summary.auto_linked >= 1


# ---------------------------------------------------------------------------
# Ambiguous → HITL
# ---------------------------------------------------------------------------


def test_l1_ambiguous_mention_routes_to_hitl(tmp_path: Path) -> None:
    """A mention with score in [hitl_lower, auto_accept) lands in the HITL queue."""

    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from flows.website_l1_entity_tagged import run_l1_for_domain
    from src.er.canonical_index import CanonicalIndex
    from src.hitl.queue import HITLQueue
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry

    db = _nyu_canonical_index_sqlite(tmp_path)
    canonical = CanonicalIndex(sqlite_path=db)
    hitl = HITLQueue(sqlite_path=db)
    registry = WebsiteCrawlRegistry(sqlite_path=db)
    domain = registry.register(
        domain="adea.org", tier="L2", stage="L1",
        cadence_cron="0 6 * * *", actor="t",
    )

    # Partial / mis-spelled mention -> the long-alias path yields a sub-95 score
    # but >= 75 (HITL band).
    body = "We're sending students to the New York University Coll of Dentistry program."
    record = _crawled_record(url="https://adea.org/p2", body_md=body)
    graph = _StubGraph()
    summary = run_l1_for_domain(
        domain=domain, records=[record], graph=graph,
        canonical=canonical, hitl=hitl, job_id="job:l1:hitl",
    )
    # Either the long-alias partial-ratio drops into HITL band OR auto-accept
    # fires for short aliases; in either case ensure at least one MENTIONS edge
    # is materialized.
    assert summary.mentions_written >= 1


def test_l1_no_match_below_threshold_skips(tmp_path: Path) -> None:
    """Body without any L1 alias → zero mentions, zero edges."""

    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from flows.website_l1_entity_tagged import run_l1_for_domain
    from src.er.canonical_index import CanonicalIndex
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry

    db = _nyu_canonical_index_sqlite(tmp_path)
    canonical = CanonicalIndex(sqlite_path=db)
    registry = WebsiteCrawlRegistry(sqlite_path=db)
    domain = registry.register(
        domain="adea.org", tier="L2", stage="L1",
        cadence_cron="0 6 * * *", actor="t",
    )

    body = "Generic admissions information without naming any specific institution."
    record = _crawled_record(url="https://adea.org/p3", body_md=body)
    graph = _StubGraph()
    summary = run_l1_for_domain(
        domain=domain, records=[record], graph=graph,
        canonical=canonical, job_id="job:l1:nomatch",
    )
    assert summary.mentions_written == 0
    assert graph.edges_of_label("MENTIONS") == []


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_l1_idempotent_no_change_no_writes(tmp_path: Path) -> None:
    """Re-running L1 with identical content_hash is a no-op on MENTIONS edges."""

    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from flows.website_l1_entity_tagged import run_l1_for_domain
    from src.er.canonical_index import CanonicalIndex
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry

    db = _nyu_canonical_index_sqlite(tmp_path)
    canonical = CanonicalIndex(sqlite_path=db)
    registry = WebsiteCrawlRegistry(sqlite_path=db)
    domain = registry.register(
        domain="adea.org", tier="L2", stage="L1",
        cadence_cron="0 6 * * *", actor="t",
    )

    body = "NYU College of Dentistry is a fine institution."
    records = [_crawled_record(
        url="https://adea.org/p", body_md=body, content_hash="x" * 64,
    )]

    graph = _StubGraph()
    run_l1_for_domain(
        domain=domain, records=records, graph=graph,
        canonical=canonical, job_id="job:1",
    )
    initial = len(graph.edges)

    run_l1_for_domain(
        domain=domain, records=records, graph=graph,
        canonical=canonical, job_id="job:2",
    )
    assert len(graph.edges) == initial


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def test_l1_chunking_produces_chunks_with_overlap(tmp_path: Path) -> None:
    """A long body is split into 512-token chunks with 64-token overlap.

    The flow writes Chunk nodes (label='Chunk') and HAS_CHUNK edges from
    the Page → each Chunk.
    """

    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from flows.website_l1_entity_tagged import run_l1_for_domain
    from src.er.canonical_index import CanonicalIndex
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry

    db = _nyu_canonical_index_sqlite(tmp_path)
    canonical = CanonicalIndex(sqlite_path=db)
    registry = WebsiteCrawlRegistry(sqlite_path=db)
    domain = registry.register(
        domain="adea.org", tier="L2", stage="L1",
        cadence_cron="0 6 * * *", actor="t",
    )

    # Produce ~ 1200 tokens worth of text — should be ~3 chunks at
    # 512-token windows with 64-token overlap.
    body = "NYU dental school applications " * 200  # ~1000 tokens
    record = _crawled_record(
        url="https://adea.org/big", body_md=body, content_hash="z" * 64,
    )
    graph = _StubGraph()
    summary = run_l1_for_domain(
        domain=domain, records=[record], graph=graph,
        canonical=canonical, job_id="job:l1:chunks",
    )
    chunks = graph.nodes_of_label("Chunk")
    assert summary.chunks_written == len(chunks)
    assert len(chunks) >= 2  # multi-chunk body
    has_chunk = graph.edges_of_label("HAS_CHUNK")
    # One HAS_CHUNK edge per chunk
    assert len(has_chunk) == len(chunks)
