"""WP4.2 / ADR-022 — Qwen3 embedder adapter (construction is lazy) + cli dispatch.

No model download here: construction must not load the 1.2 GB model (GAP-054
lazy discipline). The blocking-recall A/B that justifies the swap lives in
`evals/blocking_recall.py`.
"""

from __future__ import annotations

from src.cli import _build_embedder
from src.embeddings import HashEmbeddingService
from src.embeddings.bge_embedder import BGEEmbeddingService
from src.embeddings.qwen_embedder import QwenEmbeddingService


def test_qwen_construction_is_lazy() -> None:
    svc = QwenEmbeddingService()
    assert svc.model == "Qwen/Qwen3-Embedding-0.6B"
    assert svc.dim == 1024            # default before load
    assert svc._impl is None          # model not loaded until first embed()


def test_qwen_implements_embedding_service_protocol() -> None:
    svc = QwenEmbeddingService()
    assert hasattr(svc, "embed")
    assert hasattr(svc, "embed_batch")
    assert isinstance(svc.model, str) and svc.dim > 0


def test_build_embedder_dispatch() -> None:
    assert isinstance(_build_embedder("qwen"), QwenEmbeddingService)
    assert isinstance(_build_embedder("bge"), BGEEmbeddingService)
    assert isinstance(_build_embedder("hash"), HashEmbeddingService)
    assert isinstance(_build_embedder("anything-else"), HashEmbeddingService)
