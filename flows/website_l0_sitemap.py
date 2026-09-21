"""V1.6a — L0 sitemap flow per ADR-020.

Deterministic, no-LLM, $0. Consumes Crawl4AIAdapter output (CrawledRecords
+ per-record link/image extractions) and writes Page / MediaAsset / Table /
ExternalRef nodes + LINKS_TO / EMBEDS / TABLE_OF / BELONGS_TO_SITEMAP edges.

Idempotency contract (FR-1.6a-4.4):
- content_hash unchanged for a known URL → no-op.
- content_hash changed → close prior Page node (t_valid_to=now), open new.

This module is intentionally a plain function (not a Prefect flow yet);
Phase 7 wraps it in `flows/website_crawl_dispatcher.py`'s Prefect task.
Keeping the L0 path testable as a pure Python function lets it run in
unit tests without a Prefect runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urlparse

from src.graph.client import Edge, Node, SourceTier
from src.graph.web_node_types import (
    EXTERNAL_REF_LABEL,
    PAGE_LABEL,
    external_ref_node_id,
    make_embeds_edge,
    make_external_ref_node,
    make_links_to_edge,
    make_media_asset_node,
    make_page_node,
    make_table_node,
    make_table_of_edge,
    media_asset_node_id,
    page_node_id,
)
from src.ingestion.adapters.crawl4ai_web import CrawledRecord
from src.ingestion.sources.website_crawl import CrawlDomainRow

# ---------------------------------------------------------------------------
# Graph protocol — narrow surface the L0 flow needs
# ---------------------------------------------------------------------------


class GraphWriter(Protocol):
    """Subset of GraphClient the L0 flow uses."""

    def upsert_node(self, node: Node) -> None: ...

    def upsert_edge(self, edge: Edge) -> None: ...

    def get_node(self, node_id: str) -> Node | None: ...

    def nodes_of_label(
        self, label: str, *, limit: int = 10_000,
    ) -> list[Node]: ...


# ---------------------------------------------------------------------------
# Run-summary type — what the dispatcher reads
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class L0RunSummary:
    job_id: str
    domain_id: str
    pages_written: int
    pages_unchanged: int
    pages_closed: int       # bitemporal close-and-rewrite
    media_assets_written: int
    tables_written: int
    external_refs_written: int
    links_written: int


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_l0_for_domain(
    *,
    domain: CrawlDomainRow,
    records: list[tuple[CrawledRecord, list[str], list[str]]],
    graph: GraphWriter,
    job_id: str,
    now: datetime | None = None,
) -> L0RunSummary:
    """Write Page / Sitemap / MediaAsset / Table / ExternalRef nodes + edges.

    `records` is a list of (CrawledRecord, links_to_urls, image_urls). The
    adapter provides the CrawledRecord; the L0 flow's caller (Phase 7
    dispatcher) extracts the link + image lists from the page body once
    per page (kept out of the adapter so the adapter stays HTTP-focused).

    Returns an L0RunSummary the dispatcher records in `crawl_jobs`.
    """

    now = now or datetime.now(UTC)
    url_to_page_id, p_written, p_unchanged, p_closed = _write_page_nodes(
        records=records, domain=domain, graph=graph, now=now,
    )
    media_written = _write_media_assets(
        records=records, url_to_page_id=url_to_page_id,
        domain=domain, graph=graph, now=now,
    )
    tables_written = _write_tables(
        records=records, url_to_page_id=url_to_page_id,
        domain=domain, graph=graph, now=now,
    )
    links_written, ext_refs_written = _write_links(
        records=records, url_to_page_id=url_to_page_id,
        domain=domain, graph=graph, now=now,
    )
    return L0RunSummary(
        job_id=job_id,
        domain_id=domain.domain_id,
        pages_written=p_written,
        pages_unchanged=p_unchanged,
        pages_closed=p_closed,
        media_assets_written=media_written,
        tables_written=tables_written,
        external_refs_written=ext_refs_written,
        links_written=links_written,
    )


def _write_page_nodes(
    *,
    records: list[tuple[CrawledRecord, list[str], list[str]]],
    domain: CrawlDomainRow,
    graph: GraphWriter,
    now: datetime,
) -> tuple[dict[str, str], int, int, int]:
    """Page-write loop with bitemporal close-then-open + idempotency."""

    url_to_page_id: dict[str, str] = {}
    written = 0
    unchanged = 0
    closed_count = 0

    # Build the url -> open-Page map ONCE per run. The previous per-record
    # `_find_open_page_for_url` call was O(records x pages) and silently
    # missed pages beyond nodes_of_label's default 10K cap.
    open_by_url: dict[str, Node] = {}
    for node in graph.nodes_of_label(PAGE_LABEL, limit=1_000_000):
        if node.properties.get("t_valid_to"):
            continue
        page_url = node.properties.get("url")
        if page_url:
            open_by_url[str(page_url)] = node

    for record, _links, _images in records:
        existing = open_by_url.get(record.url)
        new_node_id = page_node_id(url=record.url, content_hash=record.content_hash)

        if existing is not None and existing.id == new_node_id:
            # Same content_hash → no-op.
            unchanged += 1
            url_to_page_id[record.url] = existing.id
            continue

        if existing is not None:
            # Different content_hash → close the prior version.
            graph.upsert_node(_close_node(existing, t_valid_to=now))
            closed_count += 1

        page = make_page_node(
            url=record.url,
            domain=record.domain,
            mime=record.mime,
            title=record.title,
            body_md=record.body_md,
            content_hash=record.content_hash,
            bytes_=record.bytes_,
            crawled_at=record.fetched_at,
            source_tier=domain.tier,
            domain_id=domain.domain_id,
            etag=record.etag,
            last_modified=record.last_modified,
            t_valid_from=now,
        )
        graph.upsert_node(page)
        written += 1
        url_to_page_id[record.url] = page.id
        open_by_url[record.url] = page

    return url_to_page_id, written, unchanged, closed_count


def _write_media_assets(
    *,
    records: list[tuple[CrawledRecord, list[str], list[str]]],
    url_to_page_id: dict[str, str],
    domain: CrawlDomainRow,
    graph: GraphWriter,
    now: datetime,
) -> int:
    seen_assets: set[str] = set()
    written = 0
    for record, _links, images in records:
        from_page_id = url_to_page_id.get(record.url)
        if from_page_id is None:
            continue
        for img_url in images:
            asset_id = media_asset_node_id(url=img_url)
            if asset_id not in seen_assets:
                graph.upsert_node(make_media_asset_node(
                    url=img_url,
                    domain=_fqdn(img_url) or record.domain,
                    source_tier=domain.tier,
                ))
                seen_assets.add(asset_id)
                written += 1
            graph.upsert_edge(make_embeds_edge(
                page_id=from_page_id, asset_id=asset_id,
                source_tier=domain.tier, valid_from=now,
            ))
    return written


def _write_tables(
    *,
    records: list[tuple[CrawledRecord, list[str], list[str]]],
    url_to_page_id: dict[str, str],
    domain: CrawlDomainRow,
    graph: GraphWriter,
    now: datetime,
) -> int:
    written = 0
    for record, _links, _images in records:
        from_page_id = url_to_page_id.get(record.url)
        if from_page_id is None:
            continue
        for table in record.tables:
            t_node = make_table_node(
                parent_url=record.url,
                parent_page_id=from_page_id,
                ordinal=table.ordinal,
                rows=table.rows,
                cols=table.cols,
                cells=table.cells,
                source_tier=domain.tier,
                caption=table.caption,
            )
            graph.upsert_node(t_node)
            written += 1
            graph.upsert_edge(make_table_of_edge(
                page_id=from_page_id, table_id=t_node.id,
                source_tier=domain.tier, valid_from=now,
            ))
    return written


def _write_links(
    *,
    records: list[tuple[CrawledRecord, list[str], list[str]]],
    url_to_page_id: dict[str, str],
    domain: CrawlDomainRow,
    graph: GraphWriter,
    now: datetime,
) -> tuple[int, int]:
    seen_ext_refs: set[str] = set()
    links_written = 0
    ext_refs_written = 0
    for record, links, _images in records:
        from_page_id = url_to_page_id.get(record.url)
        if from_page_id is None:
            continue
        for link in links:
            target = url_to_page_id.get(link)
            if target is None and _fqdn(link) != record.domain:
                # Out-of-domain → ExternalRef placeholder.
                ext_id = external_ref_node_id(url=link)
                if ext_id not in seen_ext_refs:
                    graph.upsert_node(make_external_ref_node(
                        url=link, first_seen_at=now,
                    ))
                    seen_ext_refs.add(ext_id)
                    ext_refs_written += 1
                target = ext_id
            if target is None:
                # Same-domain link to a page we haven't seen yet — skip.
                continue
            graph.upsert_edge(make_links_to_edge(
                from_page_id=from_page_id,
                to_node_id=target,
                source_tier=domain.tier,
                valid_from=now,
            ))
            links_written += 1
    return links_written, ext_refs_written


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_open_page_for_url(graph: GraphWriter, *, url: str) -> Node | None:
    """Return the currently-open Page node for `url`, or None.

    "Open" means `t_valid_to` is None / empty. There's at most one open
    version per URL by construction (close-then-open invariant).
    """

    for node in graph.nodes_of_label(PAGE_LABEL):
        if node.properties.get("url") != url:
            continue
        if not node.properties.get("t_valid_to"):
            return node
    return None


def _close_node(node: Node, *, t_valid_to: datetime) -> Node:
    """Return a copy of `node` with `t_valid_to` and `t_ingest_to` set."""

    new_props = dict(node.properties)
    iso = t_valid_to.isoformat()
    new_props["t_valid_to"] = iso
    new_props["t_ingest_to"] = iso
    return Node(
        id=node.id,
        label=node.label,
        source_tier=node.source_tier,
        properties=new_props,
    )


def _fqdn(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


__all__ = [
    "EXTERNAL_REF_LABEL",
    "GraphWriter",
    "L0RunSummary",
    "run_l0_for_domain",
]


# Note: SourceTier is imported above so type checkers see the alias used
# in the make_*_node signatures without re-exporting it.
_ = SourceTier
