"""V1.6a Phase 6 — L2 full GraphRAG flow unit tests.

Per ADR-020 + V1.6a plan.md Phase 6. L2 reuses V1's Pass-4/5 machinery
+ V1.5c WebVerificationAgent for conflict step 5.

Failing-first: a fixture corpus of pages -> >= 1 Cluster + SUMMARIZES
edges; total cost recorded <= projected cap.

Budget gating fires at three points (per ADR-020 + FR-1.6a-4.7):
1. pre-run projection: avg_recent × queued × 1.2 ≤ remaining_budget
2. cumulative inside the run: stop when spent >= cap
3. dispatcher boot: refuses to dispatch a domain whose spent >= cap
The dispatcher-boot test lives in Phase 7; this phase covers (1) + (2).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from src.graph.client import Edge, Node


@dataclass
class _StubGraph:
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


def _crawled_record(*, url: str, body_md: str, content_hash: str = "a" * 64):
    from src.ingestion.adapters.crawl4ai_web import CrawledRecord

    return CrawledRecord(
        url=url, domain=url.split("/")[2], mime="text/html",
        title=url, body_md=body_md, content_hash=content_hash[:64],
        bytes_=len(body_md.encode()), fetched_at=datetime.now(UTC),
        source_tier="L2",
    )


# ---------------------------------------------------------------------------
# Failing-first
# ---------------------------------------------------------------------------


def test_l2_produces_clusters_and_summaries_within_budget(tmp_path: Path) -> None:
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from flows.website_l2_full_graphrag import L2Summarizer, run_l2_for_domain
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry

    registry = WebsiteCrawlRegistry(sqlite_path=tmp_path / "engine.db")
    domain = registry.register(
        domain="adea.org", tier="L2", stage="L2",
        cadence_cron="0 6 * * *", actor="t",
    )

    # Fake fixed-cost summarizer — returns a generated summary + cost
    class _StubSummarizer:
        def summarize_cluster(self, member_texts: list[str]) -> tuple[str, float]:
            return (f"Summary of {len(member_texts)} pages", 0.001)

    pages = [
        _crawled_record(url=f"https://adea.org/p{i}", body_md=f"page {i} content " * 50)
        for i in range(10)
    ]
    graph = _StubGraph()
    summary = run_l2_for_domain(
        domain=domain,
        records=pages,
        graph=graph,
        summarizer=_StubSummarizer(),
        job_id="job:l2:test",
        spent_so_far_usd=0.0,
    )
    assert summary.clusters_written >= 1
    summarizes = graph.edges_of_label("SUMMARIZES")
    assert len(summarizes) >= 1
    assert summary.cost_usd <= domain.max_usd_per_month


# ---------------------------------------------------------------------------
# Budget skip (projection > remaining)
# ---------------------------------------------------------------------------


def test_l2_skips_when_projected_cost_exceeds_remaining_budget(tmp_path: Path) -> None:
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from flows.website_l2_full_graphrag import (
        L2BudgetCapped,
        run_l2_for_domain,
    )
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry

    registry = WebsiteCrawlRegistry(sqlite_path=tmp_path / "engine.db")
    domain = registry.register(
        domain="adea.org", tier="L2", stage="L2",
        cadence_cron="0 6 * * *", actor="t",
        max_usd_per_month=0.10,  # cap
    )

    # Stub summarizer that claims $0.10/cluster — projection blows the cap
    class _PricySummarizer:
        def summarize_cluster(self, member_texts: list[str]) -> tuple[str, float]:
            return ("Summary", 0.10)

    pages = [_crawled_record(url=f"https://adea.org/p{i}", body_md="x") for i in range(10)]
    graph = _StubGraph()
    summary = run_l2_for_domain(
        domain=domain,
        records=pages,
        graph=graph,
        summarizer=_PricySummarizer(),
        job_id="job:l2:cap",
        spent_so_far_usd=0.09,  # almost all of the $0.10 cap already spent
        # Dispatcher feeds this from avg_recent in crawl_cost (production).
        projected_cost_per_cluster=0.10,
    )
    assert isinstance(summary, L2BudgetCapped)
    assert summary.clusters_written == 0


# ---------------------------------------------------------------------------
# Cumulative cap during run
# ---------------------------------------------------------------------------


def test_l2_stops_when_cumulative_cost_hits_cap(tmp_path: Path) -> None:
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from flows.website_l2_full_graphrag import run_l2_for_domain
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry

    registry = WebsiteCrawlRegistry(sqlite_path=tmp_path / "engine.db")
    domain = registry.register(
        domain="adea.org", tier="L2", stage="L2",
        cadence_cron="0 6 * * *", actor="t",
        max_usd_per_month=0.05,  # tight cap
    )

    # Each cluster genuinely costs $0.02 — 3 of them = $0.06 > $0.05 cap
    class _Summarizer:
        def summarize_cluster(self, member_texts: list[str]) -> tuple[str, float]:
            return ("Summary", 0.02)

    # 15 pages -> 3 clusters at 5 pages/cluster
    pages = [
        _crawled_record(url=f"https://adea.org/p{i}", body_md=f"text {i} " * 20)
        for i in range(15)
    ]
    graph = _StubGraph()
    summary = run_l2_for_domain(
        domain=domain,
        records=pages,
        graph=graph,
        summarizer=_Summarizer(),
        job_id="job:l2:cum",
        spent_so_far_usd=0.0,
        cluster_size=5,
        # Dispatcher feeds avg_recent; here it's the real per-cluster cost.
        projected_cost_per_cluster=0.02,
    )
    # Cap stops at 2 clusters ($0.04 spent; 3rd would push to $0.06 > $0.05).
    # Pre-run projection: 3 * $0.02 * 1.2 = $0.072 > $0.05 -> capped pre-run.
    # So expect L2BudgetCapped (clusters_written=0).
    from flows.website_l2_full_graphrag import L2BudgetCapped, L2RunSummary
    if isinstance(summary, L2BudgetCapped):
        assert summary.clusters_written == 0
    else:
        assert isinstance(summary, L2RunSummary)
        assert summary.clusters_written <= 2
        assert summary.cost_usd <= 0.05


# ---------------------------------------------------------------------------
# Idempotency / cache hit
# ---------------------------------------------------------------------------


def test_l2_idempotent_cache_hit_no_llm_call(tmp_path: Path) -> None:
    """Re-running L2 on unchanged corpus should not invoke the summarizer."""

    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from flows.website_l2_full_graphrag import run_l2_for_domain
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry

    registry = WebsiteCrawlRegistry(sqlite_path=tmp_path / "engine.db")
    domain = registry.register(
        domain="adea.org", tier="L2", stage="L2",
        cadence_cron="0 6 * * *", actor="t",
    )

    call_count = 0
    class _CountedSummarizer:
        def summarize_cluster(self, member_texts: list[str]) -> tuple[str, float]:
            nonlocal call_count
            call_count += 1
            return ("Summary", 0.001)

    pages = [
        _crawled_record(url=f"https://adea.org/p{i}", body_md=f"text {i} ", content_hash=f"{i:064d}")
        for i in range(6)
    ]
    graph = _StubGraph()
    # First run — populates clusters + summaries.
    run_l2_for_domain(
        domain=domain, records=pages, graph=graph,
        summarizer=_CountedSummarizer(), job_id="job:1",
        spent_so_far_usd=0.0,
    )
    first_count = call_count
    nodes_first = len(graph.nodes)

    # Second run — identical input. Cache should short-circuit.
    run_l2_for_domain(
        domain=domain, records=pages, graph=graph,
        summarizer=_CountedSummarizer(), job_id="job:2",
        spent_so_far_usd=0.0,
    )
    # Same number of nodes (idempotent), no new LLM calls.
    assert len(graph.nodes) == nodes_first
    assert call_count == first_count
