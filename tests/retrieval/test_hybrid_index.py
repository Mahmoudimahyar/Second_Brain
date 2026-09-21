"""Tests for `src.retrieval.index.HybridIndex` (ADR-002 RRF fusion).

V1 lexical = TF-IDF (sklearn); vector = brute-force cosine kNN over BGE-style
embeddings. ADR-002 ultimately calls for BM25 + HNSW; both are wire-compatible
swaps behind the `HybridIndex` interface and considered V1.x optimizations.
"""

from __future__ import annotations

from pathlib import Path

from src.embeddings import HashEmbeddingService
from src.er.canonical_index import CanonicalIndex
from src.graph.client import Edge, Node
from src.graph.kuzu_client import KuzuGraphClient
from src.retrieval.api import RetrievalService
from src.retrieval.index import HybridIndex


def _node(node_id: str, body: str, label: str = "Post", tier: str = "L5") -> Node:
    return Node(
        id=node_id, label=label, source_tier=tier,
        properties={"body": body, "title": body[:32]},
    )


def test_empty_index_returns_empty() -> None:
    idx = HybridIndex(embedder=HashEmbeddingService())
    idx.build([])
    assert idx.search("anything") == []


def test_lexical_match_beats_unrelated() -> None:
    nodes = [
        _node("p1", "I just got accepted to Harvard School of Dental Medicine!"),
        _node("p2", "When does the DAT registration open?"),
        _node("p3", "Pumpkin spice latte review."),
    ]
    idx = HybridIndex(embedder=HashEmbeddingService())
    idx.build(nodes)

    results = idx.search("Harvard acceptance", top_k=3)

    assert results[0].node_id == "p1"
    assert all(r.fusion_score > 0 for r in results)


def test_search_returns_fewer_than_top_k_when_few_nodes() -> None:
    nodes = [_node("p1", "x")]
    idx = HybridIndex(embedder=HashEmbeddingService())
    idx.build(nodes)
    results = idx.search("x", top_k=10)
    assert len(results) <= 1


def test_search_respects_source_tier_filter() -> None:
    nodes = [
        _node("l1", "Harvard School of Dental Medicine", tier="L1"),
        _node("l5", "Harvard acceptance post", tier="L5"),
    ]
    idx = HybridIndex(embedder=HashEmbeddingService())
    idx.build(nodes)
    results = idx.search("Harvard", top_k=10, source_tier_min="L1")
    assert all(r.node.source_tier == "L1" for r in results)


def test_rrf_score_decreases_with_rank() -> None:
    """Reciprocal-rank fusion: rank-1 result should have a higher fusion_score
    than rank-2, even if both retrievers picked the same items."""

    nodes = [_node(f"p{i}", f"keyword foo {i}") for i in range(5)]
    idx = HybridIndex(embedder=HashEmbeddingService())
    idx.build(nodes)
    results = idx.search("keyword foo", top_k=5)

    assert len(results) >= 2
    scores = [r.fusion_score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_build_is_idempotent_on_same_nodes() -> None:
    nodes = [
        _node("p1", "Harvard accepted"),
        _node("p2", "Penn rejected"),
    ]
    idx = HybridIndex(embedder=HashEmbeddingService())
    idx.build(nodes)
    first = [r.node_id for r in idx.search("Harvard", top_k=2)]
    idx.build(nodes)
    second = [r.node_id for r in idx.search("Harvard", top_k=2)]
    assert first == second


def test_retrieval_service_uses_hybrid_index_when_provided(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """RetrievalService.query_graph falls through to the hybrid index for seed
    selection when one is wired in (otherwise legacy substring path)."""

    graph = KuzuGraphClient(db_path=Path(tmp_path) / "kuzu.db")
    nodes = [
        _node("post:harvard", "I got accepted to Harvard last Tuesday."),
        _node("post:upenn", "UPenn rejected my application; gutted."),
    ]
    edges = [
        Edge(id="e1", label="MENTIONS_SCHOOL", from_id="post:harvard",
             to_id="school:harvard", source_tier="L5", rank="normal",
             references=["post:harvard"]),
    ]
    graph.upsert_nodes(nodes)
    graph.upsert_edges(edges)

    sqlite_path = Path(tmp_path) / "store.db"
    idx_canonical = CanonicalIndex(sqlite_path=sqlite_path)
    hybrid = HybridIndex(embedder=HashEmbeddingService())
    hybrid.build(nodes)

    svc = RetrievalService(graph=graph, canonical_index=idx_canonical,
                            hybrid_index=hybrid)
    results = svc.query_graph("Harvard accepted", limit=2)
    graph.close()
    assert any(r.node_id == "post:harvard" for r in results)
