"""WP3.3 / GAP-051 — HybridIndex (BM25+HNSW+RRF) wired into query_graph.

`HybridIndex` was Built (and unit-tested) but never constructed in `src/`, so
the default retrieval path was a substring scan. These tests prove the index is
now the seed lookup when a `RetrievalService` is built with one.
"""

from __future__ import annotations

from pathlib import Path

from src.embeddings import HashEmbeddingService
from src.er.canonical_index import CanonicalIndex
from src.graph.client import Node
from src.graph.kuzu_client import KuzuGraphClient
from src.retrieval.api import RetrievalService
from src.retrieval.index import HybridIndex


def _graph(tmp_path: Path) -> KuzuGraphClient:
    g = KuzuGraphClient(db_path=tmp_path / "kuzu.db")
    g.upsert_node(Node(id="post:1", label="Post", source_tier="L5",
                       properties={"body": "CASPer requirement and interview timeline"}))
    g.upsert_node(Node(id="post:2", label="Post", source_tier="L5",
                       properties={"body": "financial aid and scholarships"}))
    g.upsert_node(Node(id="school:nyu", label="School", source_tier="L1",
                       properties={"name": "New York University"}))
    return g


def _svc(tmp_path: Path, *, with_hybrid: bool) -> tuple[KuzuGraphClient, HybridIndex | None, RetrievalService]:
    g = _graph(tmp_path)
    canon = CanonicalIndex(sqlite_path=tmp_path / "store.db")
    idx: HybridIndex | None = None
    if with_hybrid:
        idx = HybridIndex(embedder=HashEmbeddingService())
        idx.build(g.all_nodes())
    return g, idx, RetrievalService(graph=g, canonical_index=canon, hybrid_index=idx)


def test_seed_lookup_uses_hybrid_index_when_wired(tmp_path: Path) -> None:
    g, idx, svc = _svc(tmp_path, with_hybrid=True)
    assert idx is not None
    seeds = svc._seed_lookup("casper interview", limit=10, source_tier_min=None)
    expected = {h.node.id for h in idx.search("casper interview", top_k=10)}
    assert expected, "hybrid index returned no hits — wiring not exercised"
    assert {n.id for n in seeds} == expected
    g.close()


def test_query_graph_returns_results_via_hybrid(tmp_path: Path) -> None:
    g, _idx, svc = _svc(tmp_path, with_hybrid=True)
    results = svc.query_graph("casper interview timeline")
    assert any(r.node_id == "post:1" for r in results)
    assert all(r.references for r in results)  # NFR-4: every result cited
    g.close()


def test_substring_fallback_without_hybrid(tmp_path: Path) -> None:
    g, idx, svc = _svc(tmp_path, with_hybrid=False)
    assert idx is None
    results = svc.query_graph("casper")
    assert any(r.node_id == "post:1" for r in results)
    g.close()
