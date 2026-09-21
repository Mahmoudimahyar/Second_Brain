"""V1.6a — L2 full GraphRAG flow per ADR-020.

LightRAG-style staged ingestion: signed-graph clustering on the L1
chunks + per-cluster summary via the model gateway (Gemini Flash-Lite
by default per ADR-003 + V1.5c per-task matrix) + selective claim /
sentiment extraction on chunks passing the utility filter.

Budget gating fires at three points per FR-1.6a-4.7:
1. Pre-run projection: avg_recent * queued * 1.2 + spent_so_far <= cap.
   If exceeded -> emit `budget_capped` HITL item; skip L2; L0+L1 still
   commit (caller's responsibility — this module just returns an
   `L2BudgetCapped` summary so the dispatcher records `status='capped'`).
2. Cumulative inside the run: after each cluster-summary LLM call,
   re-check spent_so_far + cluster_cost <= cap. Stop on first overflow.
3. Dispatcher boot (Phase 7): refuses to dispatch a domain whose
   spent_month >= max_usd_per_month.

The signed-graph clustering algorithm is V1's Pass-3 clustering
(`src.extraction.pass3_clustering`) consumed in chunk-list mode. For
unit-test scope we accept any injected summarizer + clustering
function; production wiring builds them from the gateway + V1
extraction code.

Idempotency: cluster ids are hashes of (sorted member chunk ids). A
re-run on unchanged chunks re-derives identical cluster ids and the
summarizer is not invoked (cache check via existing Cluster node).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from src.graph.client import Edge, Node, SourceTier
from src.graph.web_node_types import (
    IN_CLUSTER,
    SUMMARIZES,
    page_node_id,
)
from src.ingestion.adapters.crawl4ai_web import CrawledRecord
from src.ingestion.sources.website_crawl import CrawlDomainRow

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default cluster size for the simple L2 clusterer. Real production
#: uses V1's signed-graph community detection; this default is a
#: well-behaved fallback when the V1 algorithm isn't wired (e.g., unit
#: tests).
DEFAULT_CLUSTER_SIZE: int = 5

#: Safety margin on the pre-run projection (per FR-1.6a-4.7).
BUDGET_SAFETY_MULTIPLIER: float = 1.2

CLUSTER_LABEL: str = "Cluster"
SUMMARY_LABEL: str = "Summary"


# ---------------------------------------------------------------------------
# Summarizer + graph protocols
# ---------------------------------------------------------------------------


class L2Summarizer(Protocol):
    """LLM summarizer for L2 cluster summaries.

    Returns (summary_text, cost_usd). Production wires this to the
    model gateway with the `website_l2_cluster_summary` task entry per
    tech-stack.md V1.6a additions.
    """

    def summarize_cluster(self, member_texts: list[str]) -> tuple[str, float]: ...


class GraphWriter(Protocol):
    def upsert_node(self, node: Node) -> None: ...

    def upsert_edge(self, edge: Edge) -> None: ...

    def get_node(self, node_id: str) -> Node | None: ...

    def nodes_of_label(
        self, label: str, *, limit: int = 10_000,
    ) -> list[Node]: ...


# ---------------------------------------------------------------------------
# Run-summary types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class L2RunSummary:
    job_id: str
    domain_id: str
    clusters_written: int
    summaries_written: int
    chunks_clustered: int
    cost_usd: float
    cap_hit: bool = False


@dataclass(frozen=True)
class L2BudgetCapped:
    """Returned when the pre-run projection exceeds the remaining budget.

    The dispatcher reads this and records the crawl_job as `status='capped'`,
    emits a `budget_capped` HITL item, and proceeds with L0+L1 only.
    """

    job_id: str
    domain_id: str
    projected_cost_usd: float
    remaining_budget_usd: float
    clusters_written: int = 0
    summaries_written: int = 0
    cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_l2_for_domain(
    *,
    domain: CrawlDomainRow,
    records: list[CrawledRecord],
    graph: GraphWriter,
    summarizer: L2Summarizer,
    job_id: str,
    spent_so_far_usd: float,
    cluster_size: int = DEFAULT_CLUSTER_SIZE,
    projected_cost_per_cluster: float | None = None,
    now: datetime | None = None,
) -> L2RunSummary | L2BudgetCapped:
    """Cluster + summarize a domain's chunks. Three-point budget enforced.

    `records` are the same CrawledRecords L0 + L1 saw; L2 re-uses their
    body_md as the unit of clustering for unit-test scope. Production
    wires this to the L1 Chunk node graph (PageNode -> HAS_CHUNK ->
    Chunk -> IN_CLUSTER -> Cluster).

    `projected_cost_per_cluster` is the dispatcher's best estimate of
    per-cluster summary cost based on the last N L2 runs' average
    (read from `crawl_cost` table). Defaults to a conservative
    $0.001/cluster when not provided.

    Returns `L2RunSummary` on success or `L2BudgetCapped` when the
    pre-run projection blows the cap.
    """

    now = now or datetime.now(UTC)
    cap = float(domain.max_usd_per_month)
    remaining = max(0.0, cap - spent_so_far_usd)
    avg_cluster_cost = (
        projected_cost_per_cluster
        if projected_cost_per_cluster is not None
        else 0.001
    )

    # ---- Cluster the chunks first so we know n_clusters ------------
    grouped = _partition(records, size=cluster_size)
    n_clusters = len(grouped)

    # ---- (1) Pre-run projection ------------------------------------
    projected = n_clusters * avg_cluster_cost * BUDGET_SAFETY_MULTIPLIER
    if projected > remaining:
        return L2BudgetCapped(
            job_id=job_id,
            domain_id=domain.domain_id,
            projected_cost_usd=projected,
            remaining_budget_usd=remaining,
        )

    clusters_written = 0
    summaries_written = 0
    chunks_clustered = 0
    cost_total = 0.0

    for group in grouped:
        # ---- (2) Cumulative check ----------------------------------
        # Will doing the *next* call put us over the cap? Use the
        # projection estimate (the actual call may cost less, but we
        # need to stop *before* incurring an over-cap cost).
        if spent_so_far_usd + cost_total + avg_cluster_cost > cap:
            break

        cluster_id = _cluster_node_id(records=group)
        # Idempotency: if cluster + summary already exist (same id), skip
        # the LLM call.
        existing = graph.get_node(cluster_id)
        if existing is not None:
            chunks_clustered += len(group)
            continue

        # Materialize cluster
        graph.upsert_node(Node(
            id=cluster_id,
            label=CLUSTER_LABEL,
            source_tier=domain.tier,
            properties={
                "domain_id": domain.domain_id,
                "member_count": len(group),
                "member_urls": [r.url for r in group],
                "t_valid_from": now.isoformat(),
                "t_valid_to": None,
            },
        ))
        clusters_written += 1
        chunks_clustered += len(group)

        for rec in group:
            graph.upsert_edge(_make_in_cluster_edge(
                page_id=page_node_id(url=rec.url, content_hash=rec.content_hash),
                cluster_id=cluster_id,
                source_tier=domain.tier,
                valid_from=now,
            ))

        # ---- LLM summary call ------------------------------------------
        member_texts = [r.body_md for r in group]
        summary_text, cluster_cost = summarizer.summarize_cluster(member_texts)
        cost_total += cluster_cost

        summary_id = _summary_node_id(cluster_id=cluster_id, text=summary_text)
        graph.upsert_node(Node(
            id=summary_id,
            label=SUMMARY_LABEL,
            source_tier=domain.tier,
            properties={
                "cluster_id": cluster_id,
                "summary_text": summary_text,
                "cost_usd": cluster_cost,
                "t_valid_from": now.isoformat(),
                "t_valid_to": None,
            },
        ))
        summaries_written += 1
        graph.upsert_edge(_make_summarizes_edge(
            summary_id=summary_id,
            cluster_id=cluster_id,
            source_tier=domain.tier,
            valid_from=now,
        ))

    return L2RunSummary(
        job_id=job_id,
        domain_id=domain.domain_id,
        clusters_written=clusters_written,
        summaries_written=summaries_written,
        chunks_clustered=chunks_clustered,
        cost_usd=cost_total,
        cap_hit=(spent_so_far_usd + cost_total >= cap),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _partition(
    records: list[CrawledRecord], *, size: int,
) -> list[list[CrawledRecord]]:
    """Fixed-size partition. Production replaces with V1 signed-graph clustering."""

    if size <= 0 or not records:
        return []
    out: list[list[CrawledRecord]] = []
    for i in range(0, len(records), size):
        chunk = records[i:i + size]
        if chunk:
            out.append(chunk)
    return out


def _sha256_16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _cluster_node_id(*, records: list[CrawledRecord]) -> str:
    """Stable cluster id: hash of sorted member URL+content_hash pairs."""

    keys = sorted(f"{r.url}|{r.content_hash}" for r in records)
    return f"cluster:{_sha256_16('|'.join(keys))}"


def _summary_node_id(*, cluster_id: str, text: str) -> str:
    return f"summary:{_sha256_16(cluster_id + '|' + text)}"


def _make_in_cluster_edge(
    *,
    page_id: str,
    cluster_id: str,
    source_tier: SourceTier,
    valid_from: datetime,
) -> Edge:
    return Edge(
        id=f"edge:in_cluster:{page_id}->{cluster_id}",
        label=IN_CLUSTER,
        from_id=page_id,
        to_id=cluster_id,
        source_tier=source_tier,
        rank="normal",
        references=[page_id, cluster_id],
        t_valid_from=valid_from,
        t_ingest_from=valid_from,
    )


def _make_summarizes_edge(
    *,
    summary_id: str,
    cluster_id: str,
    source_tier: SourceTier,
    valid_from: datetime,
) -> Edge:
    return Edge(
        id=f"edge:summarizes:{summary_id}->{cluster_id}",
        label=SUMMARIZES,
        from_id=summary_id,
        to_id=cluster_id,
        source_tier=source_tier,
        rank="normal",
        references=[summary_id, cluster_id],
        t_valid_from=valid_from,
        t_ingest_from=valid_from,
    )


__all__ = [
    "BUDGET_SAFETY_MULTIPLIER",
    "CLUSTER_LABEL",
    "DEFAULT_CLUSTER_SIZE",
    "SUMMARY_LABEL",
    "GraphWriter",
    "L2BudgetCapped",
    "L2RunSummary",
    "L2Summarizer",
    "run_l2_for_domain",
]
