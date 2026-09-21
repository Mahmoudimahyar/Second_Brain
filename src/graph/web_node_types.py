"""V1.6a — Graph node + edge type constants for the website-crawl source.

Per ADR-020 + data.md §"New graph node types". All new node types carry
V1's bitemporal stamps (t_valid_from/to, t_ingest_from/to), source_tier,
rank, references, qualifiers per ADR-005.

This module exposes:
- Label constants (PAGE_LABEL, SITEMAP_LABEL, ...) for use in graph
  queries and tests
- Node-ID helpers (page_node_id, sitemap_node_id, ...) — content-hash
  + URL based for stable bitemporal versioning
- Constructor functions (make_page_node, make_external_ref_node, ...)
  that return src.graph.client.Node instances with the right shape

The flow modules (website_l0_sitemap / website_l1_entity_tagged /
website_l2_full_graphrag) consume these helpers; the graph driver
(KuzuGraphClient) sees only the V1 Node / Edge types.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from src.graph.client import Edge, Node, SourceTier

# ---------------------------------------------------------------------------
# Labels — node types
# ---------------------------------------------------------------------------

PAGE_LABEL: str = "Page"
SITEMAP_LABEL: str = "Sitemap"
MEDIA_ASSET_LABEL: str = "MediaAsset"
TABLE_LABEL: str = "Table"
EXTERNAL_REF_LABEL: str = "ExternalRef"

# ---------------------------------------------------------------------------
# Labels — edge types
# ---------------------------------------------------------------------------

LINKS_TO: str = "LINKS_TO"
BELONGS_TO_SITEMAP: str = "BELONGS_TO_SITEMAP"
EMBEDS: str = "EMBEDS"
TABLE_OF: str = "TABLE_OF"

# Per data.md — extends in L1/L2:
HAS_CHUNK: str = "HAS_CHUNK"
MENTIONS: str = "MENTIONS"
REFERENCES_TOPIC: str = "REFERENCES_TOPIC"
IN_CLUSTER: str = "IN_CLUSTER"
SUMMARIZES: str = "SUMMARIZES"
CLAIMS_FROM: str = "CLAIMS_FROM"
SUPPORTS: str = "SUPPORTS"
CONTRADICTS: str = "CONTRADICTS"


# ---------------------------------------------------------------------------
# Node-ID helpers
# ---------------------------------------------------------------------------


def _sha16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def page_node_id(*, url: str, content_hash: str) -> str:
    """`page:<sha256-16-of-url+content_hash>` per data.md."""

    return f"page:{_sha16(url + '|' + content_hash)}"


def sitemap_node_id(*, url: str) -> str:
    return f"sitemap:{_sha16(url)}"


def media_asset_node_id(*, url: str) -> str:
    return f"asset:{_sha16(url)}"


def table_node_id(*, parent_url: str, ordinal: int) -> str:
    return f"table:{_sha16(f'{parent_url}|{ordinal}')}"


def external_ref_node_id(*, url: str) -> str:
    return f"extref:{_sha16(url)}"


# ---------------------------------------------------------------------------
# Node constructors
# ---------------------------------------------------------------------------


def make_page_node(
    *,
    url: str,
    domain: str,
    mime: str,
    title: str,
    body_md: str,
    content_hash: str,
    bytes_: int,
    crawled_at: datetime,
    source_tier: SourceTier,
    domain_id: str,
    etag: str | None = None,
    last_modified: str | None = None,
    t_valid_from: datetime | None = None,
    t_valid_to: datetime | None = None,
    rank: Literal["preferred", "normal", "deprecated"] = "normal",
) -> Node:
    """Create a Page Node with the full bitemporal stamp set.

    `t_valid_from` defaults to `crawled_at`; `t_valid_to` is None for
    the currently-open version. The L0 flow's close-then-open pattern
    sets `t_valid_to` on the prior version before opening a new one.
    """

    props: dict[str, Any] = {
        "url": url,
        "domain": domain,
        "mime": mime,
        "title": title,
        "body_md": body_md,
        "content_hash": content_hash,
        "bytes": bytes_,
        "crawled_at": crawled_at.isoformat(),
        "domain_id": domain_id,
        "rank": rank,
        "etag": etag,
        "last_modified": last_modified,
        "t_valid_from": (t_valid_from or crawled_at).isoformat(),
        "t_valid_to": t_valid_to.isoformat() if t_valid_to else None,
        "t_ingest_from": crawled_at.isoformat(),
        "t_ingest_to": None,
    }
    return Node(
        id=page_node_id(url=url, content_hash=content_hash),
        label=PAGE_LABEL,
        source_tier=source_tier,
        properties=props,
    )


def make_sitemap_node(
    *,
    url: str,
    domain: str,
    urlset_count: int,
    last_fetched: datetime,
    source_tier: SourceTier,
    sub_sitemaps: list[str] | None = None,
) -> Node:
    return Node(
        id=sitemap_node_id(url=url),
        label=SITEMAP_LABEL,
        source_tier=source_tier,
        properties={
            "url": url,
            "domain": domain,
            "urlset_count": urlset_count,
            "last_fetched": last_fetched.isoformat(),
            "sub_sitemaps": sub_sitemaps or [],
        },
    )


def make_media_asset_node(
    *,
    url: str,
    domain: str,
    mime: str = "image/*",
    alt: str | None = None,
    bytes_: int | None = None,
    source_tier: SourceTier = "L2",
    ocr_text: str | None = None,
    ocr_engine: str | None = None,
) -> Node:
    return Node(
        id=media_asset_node_id(url=url),
        label=MEDIA_ASSET_LABEL,
        source_tier=source_tier,
        properties={
            "url": url,
            "domain": domain,
            "mime": mime,
            "alt": alt,
            "bytes": bytes_,
            "ocr_text": ocr_text,
            "ocr_engine": ocr_engine,
        },
    )


def make_table_node(
    *,
    parent_url: str,
    parent_page_id: str,
    ordinal: int,
    rows: int,
    cols: int,
    cells: list[list[str]],
    source_tier: SourceTier = "L2",
    caption: str | None = None,
) -> Node:
    return Node(
        id=table_node_id(parent_url=parent_url, ordinal=ordinal),
        label=TABLE_LABEL,
        source_tier=source_tier,
        properties={
            "parent_page_id": parent_page_id,
            "ordinal": ordinal,
            "caption": caption,
            "rows": rows,
            "cols": cols,
            "cells_json": json.dumps(cells),
        },
    )


def make_external_ref_node(
    *,
    url: str,
    first_seen_at: datetime,
) -> Node:
    return Node(
        id=external_ref_node_id(url=url),
        label=EXTERNAL_REF_LABEL,
        source_tier="L2",
        properties={
            "url": url,
            "first_seen_at": first_seen_at.isoformat(),
        },
    )


# ---------------------------------------------------------------------------
# Edge constructors
# ---------------------------------------------------------------------------


def make_links_to_edge(
    *,
    from_page_id: str,
    to_node_id: str,
    source_tier: SourceTier,
    valid_from: datetime,
) -> Edge:
    return Edge(
        id=f"edge:links_to:{from_page_id}->{to_node_id}",
        label=LINKS_TO,
        from_id=from_page_id,
        to_id=to_node_id,
        source_tier=source_tier,
        rank="normal",
        references=[from_page_id, to_node_id],
        t_valid_from=valid_from,
        t_ingest_from=valid_from,
    )


def make_belongs_to_sitemap_edge(
    *,
    page_id: str,
    sitemap_id: str,
    source_tier: SourceTier,
    valid_from: datetime,
) -> Edge:
    return Edge(
        id=f"edge:belongs_to_sitemap:{page_id}->{sitemap_id}",
        label=BELONGS_TO_SITEMAP,
        from_id=page_id,
        to_id=sitemap_id,
        source_tier=source_tier,
        rank="normal",
        references=[page_id, sitemap_id],
        t_valid_from=valid_from,
        t_ingest_from=valid_from,
    )


def make_embeds_edge(
    *,
    page_id: str,
    asset_id: str,
    source_tier: SourceTier,
    valid_from: datetime,
) -> Edge:
    return Edge(
        id=f"edge:embeds:{page_id}->{asset_id}",
        label=EMBEDS,
        from_id=page_id,
        to_id=asset_id,
        source_tier=source_tier,
        rank="normal",
        references=[page_id, asset_id],
        t_valid_from=valid_from,
        t_ingest_from=valid_from,
    )


def make_table_of_edge(
    *,
    page_id: str,
    table_id: str,
    source_tier: SourceTier,
    valid_from: datetime,
) -> Edge:
    return Edge(
        id=f"edge:table_of:{page_id}->{table_id}",
        label=TABLE_OF,
        from_id=page_id,
        to_id=table_id,
        source_tier=source_tier,
        rank="normal",
        references=[page_id, table_id],
        t_valid_from=valid_from,
        t_ingest_from=valid_from,
    )


__all__ = [
    "BELONGS_TO_SITEMAP",
    "CLAIMS_FROM",
    "CONTRADICTS",
    "EMBEDS",
    "EXTERNAL_REF_LABEL",
    "HAS_CHUNK",
    "IN_CLUSTER",
    "LINKS_TO",
    "MEDIA_ASSET_LABEL",
    "MENTIONS",
    "PAGE_LABEL",
    "REFERENCES_TOPIC",
    "SITEMAP_LABEL",
    "SUMMARIZES",
    "SUPPORTS",
    "TABLE_LABEL",
    "TABLE_OF",
    "external_ref_node_id",
    "make_belongs_to_sitemap_edge",
    "make_embeds_edge",
    "make_external_ref_node",
    "make_links_to_edge",
    "make_media_asset_node",
    "make_page_node",
    "make_sitemap_node",
    "make_table_node",
    "make_table_of_edge",
    "media_asset_node_id",
    "page_node_id",
    "sitemap_node_id",
    "table_node_id",
]
