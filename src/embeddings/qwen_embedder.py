"""Qwen3-Embedding-0.6B blocking embedder (ADR-022 / Q-030 → Qwen3, Apache-2.0).

Upgrade path from `bge-small-en-v1.5` (2023) chosen in WP4.2: Qwen3-Embedding-0.6B
(Jun 2025) is a stronger retrieval embedder at ~2x footprint, runs on the GTX
1080, and is Apache-2.0 (no Gemma-terms gate). Implements the `EmbeddingService`
Protocol so it drops in behind `EmbeddingService` and rolls back to BGE in one
line. Lazy + CPU-default (GAP-054); honors `CUDA_VISIBLE_DEVICES`.

Ship only if blocking recall >= BGE on the rebuilt adversarial gold
(`evals/blocking_recall.py`).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from src.embeddings.api import Embedding
from src.embeddings.bge_embedder import resolve_device


@dataclass
class QwenEmbeddingService:
    """1024-dim embeddings via `Qwen/Qwen3-Embedding-0.6B` (sentence-transformers).

    First instantiation downloads the model (~1.2 GB) to the HF cache. Inference
    is CPU-only by default; pass ``device='cuda'`` (or ``'auto'``) to use the GPU.
    """

    model_name: str = "Qwen/Qwen3-Embedding-0.6B"
    device: str = "cpu"
    batch_size: int = 16
    normalize: bool = True

    model: str = field(init=False)
    dim: int = field(init=False, default=1024)
    _impl: Any | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.model = self.model_name

    def _ensure_impl(self) -> Any:
        if self._impl is not None:
            return self._impl
        try:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        except ImportError as e:  # pragma: no cover
            raise ImportError(
                "QwenEmbeddingService requires sentence-transformers. "
                "Install with `pip install sentence-transformers`.",
            ) from e
        self._impl = SentenceTransformer(self.model_name, device=resolve_device(self.device))
        get_dim = getattr(self._impl, "get_embedding_dimension", None) or (
            self._impl.get_sentence_embedding_dimension
        )
        resolved = get_dim()
        if isinstance(resolved, int) and resolved > 0:
            self.dim = resolved
        return self._impl

    def embed(self, text: str) -> Embedding:
        impl = self._ensure_impl()
        vec = impl.encode(
            [text or ""], batch_size=1, normalize_embeddings=self.normalize,
            show_progress_bar=False,
        )
        return Embedding(
            text=text, vector=tuple(float(v) for v in vec[0]), model=self.model_name,
        )

    def embed_batch(self, texts: Iterable[str]) -> list[Embedding]:
        impl = self._ensure_impl()
        materialized = [t or "" for t in texts]
        if not materialized:
            return []
        vecs = impl.encode(
            materialized, batch_size=self.batch_size,
            normalize_embeddings=self.normalize, show_progress_bar=False,
        )
        return [
            Embedding(text=t, vector=tuple(float(v) for v in row), model=self.model_name)
            for t, row in zip(materialized, vecs, strict=True)
        ]
