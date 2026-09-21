"""V1.5b Phase 5 — `BlocklistFilter` (FR-1.5b-7.4).

Post-hoc safety net applied to Pass-4 extractions: drops any extraction
that (a) exactly matches a blocklisted pattern (canonical form), or
(b) has cosine similarity > 0.92 to a blocklisted embedding.

Dropped items are NOT silently discarded — they write `audit_log` rows
with `kind=blocklist_filtered` so operators can audit + reverse via
`/settings/feedback-loop`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from src.embeddings.api import Embedding, EmbeddingService
from src.extraction.feedback_context import ContextBlocklistEntry


@dataclass(frozen=True)
class FilterResult[T]:
    """Result of applying the blocklist to a batch of extractions."""

    kept: list[T]
    dropped: list[tuple[T, str]]   # (extraction, reason)


@dataclass
class BlocklistFilter:
    """Drops extractions matching blocklist patterns (exact OR semantic)."""

    embedding_service: EmbeddingService
    cosine_threshold: float = 0.92

    def apply[T](
        self,
        extractions: list[T],
        blocklist: list[ContextBlocklistEntry],
        *,
        pattern_of: Any = None,
    ) -> FilterResult[T]:
        """Filter extractions against the blocklist.

        `pattern_of` is an optional callable extracting the comparison
        string from each extraction (defaults to `str(extraction)`).
        """

        if not extractions or not blocklist:
            return FilterResult(kept=list(extractions), dropped=[])

        get_pattern = pattern_of if pattern_of is not None else str

        canonical_blocklist: set[str] = {
            b.pattern_canonical for b in blocklist
        }
        bl_embeddings: list[Embedding] = [
            self.embedding_service.embed(b.pattern) for b in blocklist
        ]

        kept: list[T] = []
        dropped: list[tuple[T, str]] = []
        for extraction in extractions:
            pattern_text = str(get_pattern(extraction))
            canonical = " ".join(pattern_text.lower().split())
            if canonical in canonical_blocklist:
                dropped.append((extraction, "exact_blocklist_match"))
                continue
            ext_emb = self.embedding_service.embed(pattern_text)
            best_sim = max(
                (_cosine(ext_emb, bl_emb) for bl_emb in bl_embeddings),
                default=0.0,
            )
            if best_sim > self.cosine_threshold:
                dropped.append((
                    extraction,
                    f"semantic_blocklist_match:{best_sim:.3f}",
                ))
                continue
            kept.append(extraction)

        return FilterResult(kept=kept, dropped=dropped)


def _cosine(a: Embedding, b: Embedding) -> float:
    if len(a.vector) != len(b.vector):
        return 0.0
    dot = sum(x * y for x, y in zip(a.vector, b.vector, strict=True))
    na = math.sqrt(sum(x * x for x in a.vector))
    nb = math.sqrt(sum(x * x for x in b.vector))
    if na == 0 or nb == 0:
        return 0.0
    return float(dot / (na * nb))


__all__ = ["BlocklistFilter", "FilterResult"]
