"""BGE-small-en-v1.5 embedder via sentence-transformers. Implements `EmbeddingService`.

First instantiation downloads the model (~130MB). The model is cached under
`~/.cache/huggingface/hub/` by default. Inference is CPU-only by default; pass
`device='cuda'` to use GPU when available.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from src.embeddings.api import Embedding


def resolve_device(requested: str) -> str:
    """Resolve the torch device, honoring ``CUDA_VISIBLE_DEVICES`` (GAP-054).

    The V1 host is a flaky Pascal GTX 1080 whose GPU crashes wedged the
    round-1 ingest (Q-028). Pass 1-2 need no GPU and never construct this
    embedder; Pass 3 does, but must be able to be forced onto CPU.

    - ``CUDA_VISIBLE_DEVICES=""`` (GPU explicitly disabled) -> always ``cpu``,
      even if ``cuda`` was requested.
    - ``auto`` -> ``cuda`` iff torch reports a usable GPU, else ``cpu``.
    - explicit ``cpu`` / ``cuda`` -> respected (subject to the disable rule).
    """

    cvd = os.environ.get("CUDA_VISIBLE_DEVICES")
    if cvd is not None and cvd.strip() == "":
        return "cpu"
    if requested == "auto":
        try:
            import torch  # noqa: PLC0415

            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:  # pragma: no cover - torch always present in venv
            return "cpu"
    return requested


@dataclass
class BGEEmbeddingService:
    """384-dim sentence embeddings via BAAI/bge-small-en-v1.5.

    Loaded lazily on first `embed` call. Replace HashEmbeddingService with this
    class in production by changing one import:

        # was: from src.embeddings import HashEmbeddingService
        from src.embeddings.bge_embedder import BGEEmbeddingService
        embedder = BGEEmbeddingService()
    """

    model_name: str = "BAAI/bge-small-en-v1.5"
    device: str = "cpu"
    batch_size: int = 32
    normalize: bool = True

    model: str = field(init=False)
    dim: int = field(init=False, default=384)
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
                "BGEEmbeddingService requires sentence-transformers. "
                "Install with `pip install sentence-transformers`.",
            ) from e
        self._impl = SentenceTransformer(self.model_name, device=resolve_device(self.device))
        return self._impl

    def embed(self, text: str) -> Embedding:
        impl = self._ensure_impl()
        vec = impl.encode(
            [text or ""], batch_size=1, normalize_embeddings=self.normalize,
            show_progress_bar=False,
        )
        return Embedding(text=text, vector=tuple(float(v) for v in vec[0]),
                         model=self.model_name)

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
            Embedding(text=t, vector=tuple(float(v) for v in row),
                      model=self.model_name)
            for t, row in zip(materialized, vecs, strict=True)
        ]
