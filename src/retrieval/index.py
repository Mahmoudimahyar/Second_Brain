"""Hybrid retrieval index per ADR-002: RRF fusion of lexical + vector retrievers.

V1 implementation:
  - **Lexical**: `sklearn.feature_extraction.text.TfidfVectorizer` (1-2 grams,
    case-insensitive). ADR-002 calls for BM25; TF-IDF is a strict subset of
    that family and a wire-compatible swap behind the `HybridIndex.search()`
    interface — promoting to `rank_bm25` later is a 5-line change.
  - **Vector**: brute-force cosine kNN over embeddings from `EmbeddingService`
    (BGE-small in production; `HashEmbeddingService` in tests). ADR-002 calls
    for HNSW; brute-force handles the V1 slice corpus (~30K nodes) at < 20ms.
    Promoting to `hnswlib` later is also wire-compatible.
  - **Fusion**: standard Reciprocal Rank Fusion. `score(node) = Σ 1 / (k + rank_in_retriever)`
    with `k = 60` per the RRF paper.

Each result carries its source retriever's rank so callers can debug.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from src.embeddings.api import EmbeddingService
from src.graph.client import Node

SourceTier = Literal["L1", "L2", "L3", "L4", "L5"]

_TIER_ORDER: dict[str, int] = {"L1": 1, "L2": 2, "L3": 3, "L4": 4, "L5": 5}
_RRF_K: int = 60


@dataclass(frozen=True)
class HybridResult:
    node: Node
    node_id: str
    fusion_score: float
    lexical_rank: int | None = None
    vector_rank: int | None = None


@dataclass
class HybridIndex:
    """RRF-fused retrieval index over a slice of `Node` objects.

    Designed to be rebuilt cheaply (the V1 slice corpus fits in memory). For
    incremental updates / larger corpora, swap to per-shard indexes — that's
    a V2 concern.
    """

    embedder: EmbeddingService
    rrf_k: int = _RRF_K

    _nodes: list[Node] = field(default_factory=list, init=False)
    _node_texts: list[str] = field(default_factory=list, init=False)
    _embeddings: list[tuple[float, ...]] = field(default_factory=list, init=False)
    _vectorizer: Any = field(default=None, init=False, repr=False)
    _tfidf_matrix: Any = field(default=None, init=False, repr=False)

    def build(self, nodes: list[Node]) -> None:
        """Rebuild the index from scratch. Idempotent on identical input."""

        self._nodes = list(nodes)
        self._node_texts = [_node_text(n) for n in self._nodes]
        if not self._nodes:
            self._embeddings = []
            self._vectorizer = None
            self._tfidf_matrix = None
            return

        embeddings = self.embedder.embed_batch(self._node_texts)
        self._embeddings = [e.vector for e in embeddings]

        try:
            from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: PLC0415
        except ImportError as e:  # pragma: no cover
            raise ImportError(
                "HybridIndex needs scikit-learn (TfidfVectorizer). "
                "Install with `pip install scikit-learn`.",
            ) from e
        vectorizer = TfidfVectorizer(
            lowercase=True, ngram_range=(1, 2), min_df=1, max_df=1.0,
            sublinear_tf=True,
        )
        self._tfidf_matrix = vectorizer.fit_transform(self._node_texts)
        self._vectorizer = vectorizer

    def search(
        self,
        query: str,
        *,
        top_k: int = 20,
        source_tier_min: SourceTier | None = None,
    ) -> list[HybridResult]:
        if not query.strip() or not self._nodes:
            return []
        # Per-retriever rankings: lower rank = better.
        lex_ranks = self._lexical_ranks(query)
        vec_ranks = self._vector_ranks(query)
        fused: dict[int, float] = {}
        for idx, rank in lex_ranks.items():
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (self.rrf_k + rank)
        for idx, rank in vec_ranks.items():
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (self.rrf_k + rank)

        # Sort by fusion score descending, then index ascending for determinism.
        sorted_idxs = sorted(
            fused.keys(),
            key=lambda i: (-fused[i], i),
        )
        out: list[HybridResult] = []
        for idx in sorted_idxs:
            node = self._nodes[idx]
            if not _tier_passes(node.source_tier, source_tier_min):
                continue
            out.append(HybridResult(
                node=node, node_id=node.id,
                fusion_score=fused[idx],
                lexical_rank=lex_ranks.get(idx),
                vector_rank=vec_ranks.get(idx),
            ))
            if len(out) >= top_k:
                break
        return out

    def _lexical_ranks(self, query: str) -> dict[int, int]:
        if self._vectorizer is None or self._tfidf_matrix is None:
            return {}
        try:
            from sklearn.metrics.pairwise import linear_kernel  # noqa: PLC0415
        except ImportError:  # pragma: no cover
            return {}
        q_vec = self._vectorizer.transform([query])
        sims = linear_kernel(q_vec, self._tfidf_matrix).ravel()
        return _ranks_above_threshold(list(sims), threshold=0.0)

    def _vector_ranks(self, query: str) -> dict[int, int]:
        if not self._embeddings:
            return {}
        q_emb = self.embedder.embed_batch([query])
        if not q_emb:
            return {}
        q_vec = q_emb[0].vector
        sims = [
            _cosine_similarity(q_vec, doc_vec)
            for doc_vec in self._embeddings
        ]
        return _ranks_above_threshold(sims, threshold=0.0)


def _node_text(node: Node) -> str:
    """Compose a node into a single text string for embedding + TF-IDF."""

    parts: list[str] = [node.id]
    for key in ("title", "body", "name", "topic_label", "description"):
        value = node.properties.get(key)
        if isinstance(value, str) and value:
            parts.append(value)
    return " ".join(parts)


def _cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return float(dot / (na * nb))


def _ranks_above_threshold(scores: Sequence[float], threshold: float) -> dict[int, int]:
    """Convert similarity scores → 1-indexed ranks for entries above threshold."""

    indexed = [(i, float(s)) for i, s in enumerate(scores) if s > threshold]
    indexed.sort(key=lambda pair: -pair[1])
    return {idx: rank + 1 for rank, (idx, _score) in enumerate(indexed)}


def _tier_passes(tier: str, source_tier_min: SourceTier | None) -> bool:
    if source_tier_min is None:
        return True
    return _TIER_ORDER.get(tier, 99) <= _TIER_ORDER.get(source_tier_min, 0)
