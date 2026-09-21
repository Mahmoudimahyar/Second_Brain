"""`search_codebase(query, ...)` — hybrid BM25 + filter search over indexed nodes.

V1 uses SQLite FTS5 (`SQLiteGraphClient.search_text`). HNSW vector ranking is Phase 3.5; once
landed, this primitive will fuse the two via Reciprocal Rank Fusion (RRF) per ADR-002.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from tools.graphrag.store.sqlite_client import SQLiteGraphClient
from tools.graphrag.types import NodeType


@dataclass(frozen=True)
class SearchResult:
    node_id: str
    node_type: str
    source_path: str | None
    snippet: str
    score: float


_FTS_SPECIAL_CHARS_RE = re.compile(r'["()*:]')


def _quote_query(query: str) -> str:
    """Sanitise a free-text query for FTS5.

    Each token is double-quoted to neutralise FTS5 syntax characters, then OR-joined so the
    BM25 scorer ranks documents that match any of the tokens (with higher scores for documents
    matching more tokens). This mirrors typical hybrid-search semantics.
    """

    cleaned = _FTS_SPECIAL_CHARS_RE.sub(" ", query).strip()
    tokens = [t for t in cleaned.split() if t]
    if not tokens:
        return ""
    return " OR ".join(f'"{t}"' for t in tokens)


def search_codebase(
    store: SQLiteGraphClient,
    query: str,
    *,
    kind_filter: tuple[NodeType, ...] = (),
    limit: int = 20,
) -> list[SearchResult]:
    """Hybrid BM25 (V1) search across docs / code / tests / ADRs / known issues."""

    if not query.strip():
        return []
    fts_query = _quote_query(query)
    if not fts_query:
        return []
    hits = store.search_text(fts_query, node_types=kind_filter, limit=limit)
    return [
        SearchResult(
            node_id=hit.node.id,
            node_type=hit.node.node_type.value,
            source_path=hit.node.source_path,
            snippet=hit.snippet,
            score=hit.score,
        )
        for hit in hits
    ]
