"""V1.6a Phase 4 — L0 sitemap flow unit tests.

Per ADR-020 + V1.6a plan.md Phase 4. The L0 flow turns Crawl4AIAdapter
output (CrawledRecords + their embedded TableRecords + image URLs) into
graph nodes + edges:

- Page node per URL (bitemporal per ADR-005)
- Sitemap node per discovered sitemap.xml
- MediaAsset node per image/video reference
- Table node per HTML <table>
- ExternalRef placeholder for out-of-domain links
- LINKS_TO / BELONGS_TO_SITEMAP / EMBEDS / TABLE_OF edges

Idempotency contract (FR-1.6a-4.4): re-running on unchanged content_hash
is a no-op. Changed content_hash closes prior Page node (t_valid_to=now)
and opens a new one (t_valid_from=now).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from src.graph.client import Edge, Node


@dataclass
class _StubGraph:
    """Minimal in-memory graph backing for L0 flow tests.

    Mimics Kuzu's upsert-by-id semantics — repeat calls to
    `upsert_edge(edge)` with the same edge.id update the existing entry
    rather than appending a duplicate. This matters for idempotency tests
    where the L0 flow re-derives the same edge ids on a re-run.
    """

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


def _crawled_record(
    *,
    url: str,
    body_md: str = "Hello world",
    content_hash: str = "abc123" * 10 + "abcd",  # 64 chars
    mime: str = "text/html",
    title: str = "Test page",
    links_to: list[str] | None = None,
    images: list[str] | None = None,
    tables: list[tuple[int, int, list[list[str]]]] | None = None,
):
    """Test helper — build a CrawledRecord with the fields the L0 flow consumes."""
    from src.ingestion.adapters.crawl4ai_web import CrawledRecord, TableRecord

    table_records = [
        TableRecord(ordinal=i, rows=rows, cols=cols, cells=cells)
        for i, (rows, cols, cells) in enumerate(tables or [])
    ]
    record = CrawledRecord(
        url=url,
        domain=url.split("/")[2],
        mime=mime,
        title=title,
        body_md=body_md,
        content_hash=content_hash[:64],
        bytes_=len(body_md.encode("utf-8")),
        fetched_at=datetime.now(UTC),
        source_tier="L2",
        etag=None,
        last_modified=None,
        via_proxy=False,
        cache_hit=False,
        tables=table_records,
    )
    # Embed links + images as auxiliary attributes via a wrapping struct
    # the flow will consume. The CrawledRecord dataclass is frozen, so
    # the flow takes (record, links, images) as separate args.
    return record, list(links_to or []), list(images or [])


# ---------------------------------------------------------------------------
# Failing-first
# ---------------------------------------------------------------------------


def test_l0_writes_page_nodes_and_links_to_edges(tmp_path: Path) -> None:
    """Three pages cross-linking: assert 3 Page nodes + correct LINKS_TO edges."""
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry
    from flows.website_l0_sitemap import run_l0_for_domain

    registry = WebsiteCrawlRegistry(sqlite_path=tmp_path / "engine.db")
    domain = registry.register(
        domain="adea.org", tier="L2", stage="L1",
        cadence_cron="0 6 * * *", actor="t",
    )

    pages = [
        _crawled_record(
            url="https://adea.org/page1",
            links_to=["https://adea.org/page2", "https://adea.org/page3"],
        ),
        _crawled_record(
            url="https://adea.org/page2",
            links_to=["https://adea.org/page3"],
        ),
        _crawled_record(
            url="https://adea.org/page3",
            links_to=[],
        ),
    ]

    graph = _StubGraph()
    summary = run_l0_for_domain(
        domain=domain,
        records=pages,
        graph=graph,
        job_id="job:test",
    )

    page_nodes = graph.nodes_of_label("Page")
    assert len(page_nodes) == 3
    links_to_edges = graph.edges_of_label("LINKS_TO")
    # page1 -> 2 + page1 -> 3 + page2 -> 3 = 3 edges
    assert len(links_to_edges) == 3
    assert summary.pages_written == 3
    assert summary.links_written == 3


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_l0_idempotent_no_change_no_writes(tmp_path: Path) -> None:
    """Re-running L0 on unchanged content is a no-op on the graph."""
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry
    from flows.website_l0_sitemap import run_l0_for_domain

    registry = WebsiteCrawlRegistry(sqlite_path=tmp_path / "engine.db")
    domain = registry.register(
        domain="adea.org", tier="L2", stage="L1",
        cadence_cron="0 6 * * *", actor="t",
    )

    pages = [_crawled_record(url="https://adea.org/page1", content_hash="aaaa" * 16)]
    graph = _StubGraph()
    run_l0_for_domain(domain=domain, records=pages, graph=graph, job_id="job:1")
    initial_nodes = len(graph.nodes)
    initial_edges = len(graph.edges)

    # Re-run with identical content_hash.
    run_l0_for_domain(domain=domain, records=pages, graph=graph, job_id="job:2")
    assert len(graph.nodes) == initial_nodes
    assert len(graph.edges) == initial_edges


# ---------------------------------------------------------------------------
# Bitemporal close-then-open on content_hash change
# ---------------------------------------------------------------------------


def test_l0_content_hash_change_writes_new_version_bitemporal(
    tmp_path: Path,
) -> None:
    """content_hash change -> prior Page t_valid_to closed; new node opened."""
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry
    from flows.website_l0_sitemap import run_l0_for_domain

    registry = WebsiteCrawlRegistry(sqlite_path=tmp_path / "engine.db")
    domain = registry.register(
        domain="adea.org", tier="L2", stage="L1",
        cadence_cron="0 6 * * *", actor="t",
    )

    graph = _StubGraph()
    v1 = [_crawled_record(url="https://adea.org/page1", content_hash="a" * 64)]
    run_l0_for_domain(domain=domain, records=v1, graph=graph, job_id="job:1")
    v1_nodes = graph.nodes_of_label("Page")
    assert len(v1_nodes) == 1
    v1_node_id = v1_nodes[0].id

    v2 = [_crawled_record(url="https://adea.org/page1", content_hash="b" * 64)]
    run_l0_for_domain(domain=domain, records=v2, graph=graph, job_id="job:2")
    all_page_nodes = graph.nodes_of_label("Page")
    # Two Page nodes for the same URL — one closed, one open.
    assert len(all_page_nodes) == 2
    # The prior node has t_valid_to set; the new node has t_valid_to=None.
    closed = [n for n in all_page_nodes if n.id == v1_node_id][0]
    new = [n for n in all_page_nodes if n.id != v1_node_id][0]
    assert closed.properties.get("t_valid_to") is not None
    assert new.properties.get("t_valid_to") in (None, "")


# ---------------------------------------------------------------------------
# External-link placeholder
# ---------------------------------------------------------------------------


def test_l0_external_link_creates_externalref_placeholder(tmp_path: Path) -> None:
    """A LINKS_TO whose target is out-of-domain points to an ExternalRef node."""
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry
    from flows.website_l0_sitemap import run_l0_for_domain

    registry = WebsiteCrawlRegistry(sqlite_path=tmp_path / "engine.db")
    domain = registry.register(
        domain="adea.org", tier="L2", stage="L1",
        cadence_cron="0 6 * * *", actor="t",
    )

    pages = [
        _crawled_record(
            url="https://adea.org/page1",
            links_to=["https://other.invalid/about"],
        ),
    ]
    graph = _StubGraph()
    run_l0_for_domain(domain=domain, records=pages, graph=graph, job_id="job:1")
    ext_refs = graph.nodes_of_label("ExternalRef")
    assert len(ext_refs) == 1
    assert ext_refs[0].properties["url"] == "https://other.invalid/about"


# ---------------------------------------------------------------------------
# Embeds + Tables
# ---------------------------------------------------------------------------


def test_l0_writes_mediaasset_and_embeds_edges(tmp_path: Path) -> None:
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry
    from flows.website_l0_sitemap import run_l0_for_domain

    registry = WebsiteCrawlRegistry(sqlite_path=tmp_path / "engine.db")
    domain = registry.register(
        domain="adea.org", tier="L2", stage="L1",
        cadence_cron="0 6 * * *", actor="t",
    )

    pages = [
        _crawled_record(
            url="https://adea.org/page1",
            images=[
                "https://adea.org/img/banner.jpg",
                "https://adea.org/img/chart.png",
            ],
        ),
    ]
    graph = _StubGraph()
    run_l0_for_domain(domain=domain, records=pages, graph=graph, job_id="job:1")
    assets = graph.nodes_of_label("MediaAsset")
    embeds = graph.edges_of_label("EMBEDS")
    assert len(assets) == 2
    assert len(embeds) == 2


def test_l0_writes_table_and_table_of_edges(tmp_path: Path) -> None:
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry
    from flows.website_l0_sitemap import run_l0_for_domain

    registry = WebsiteCrawlRegistry(sqlite_path=tmp_path / "engine.db")
    domain = registry.register(
        domain="adea.org", tier="L2", stage="L1",
        cadence_cron="0 6 * * *", actor="t",
    )

    pages = [
        _crawled_record(
            url="https://adea.org/coa",
            tables=[
                (2, 2, [["2024-25", "$87,000"], ["2023-24", "$85,000"]]),
            ],
        ),
    ]
    graph = _StubGraph()
    run_l0_for_domain(domain=domain, records=pages, graph=graph, job_id="job:1")
    tables = graph.nodes_of_label("Table")
    table_of = graph.edges_of_label("TABLE_OF")
    assert len(tables) == 1
    assert tables[0].properties["rows"] == 2
    assert tables[0].properties["cols"] == 2
    assert len(table_of) == 1
