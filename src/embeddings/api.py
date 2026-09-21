from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Embedding:
    text: str
    vector: tuple[float, ...]   # immutable so the dataclass remains frozen-hashable
    model: str


class EmbeddingService(Protocol):
    model: str
    dim: int

    def embed(self, text: str) -> Embedding: ...
    def embed_batch(self, texts: Iterable[str]) -> list[Embedding]: ...
