from __future__ import annotations

import math
import struct
from collections.abc import Iterable
from hashlib import sha256

from src.embeddings.api import Embedding


class HashEmbeddingService:
    """Deterministic hash-based pseudo-embedding for offline dev + tests.

    Same text → same vector across processes. Different texts produce vectors
    that are not semantically meaningful (it's a hash, not a learned embedding),
    but the Protocol contract holds — drop-in replaceable with `BGEEmbeddingService`
    once sentence-transformers is wired.
    """

    def __init__(self, dim: int = 384) -> None:
        if dim <= 0 or dim % 8 != 0:
            raise ValueError(f"dim must be a positive multiple of 8, got {dim}")
        self.model = "hash-stub-v1"
        self.dim = dim

    def embed(self, text: str) -> Embedding:
        normalized = (text or "").strip()
        needed = self.dim * 4
        buf = bytearray()
        seed = sha256(normalized.encode("utf-8")).digest()
        while len(buf) < needed:
            buf.extend(seed)
            seed = sha256(seed).digest()
        raw = [
            struct.unpack_from(">I", buf, i * 4)[0] / (1 << 32) * 2 - 1
            for i in range(self.dim)
        ]
        norm = math.sqrt(sum(v * v for v in raw))
        if norm > 0:
            raw = [v / norm for v in raw]
        return Embedding(text=text, vector=tuple(raw), model=self.model)

    def embed_batch(self, texts: Iterable[str]) -> list[Embedding]:
        return [self.embed(t) for t in texts]


def cosine_similarity(a: Embedding, b: Embedding) -> float:
    """Standard cosine sim. Both vectors are L2-normalized → dot product."""

    return float(sum(x * y for x, y in zip(a.vector, b.vector, strict=True)))
