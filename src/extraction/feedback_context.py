"""V1.5b Phase 5 — `FeedbackContextLoader` (ADR-018).

Builds a `ContextBlock` for each Pass-4 BAML template invocation:
- ≤ 4 positive examples selected via active-learning hybrid scoring
  (relevance x recency x diversity x frequency).
- ≤ 50 blocklist entries selected via LFU+LRU eviction beyond the cap.

The 4-example hard cap mirrors 2026 few-shot-collapse research.

Output is hashed (`feedback_context_hash`) so the Pass-4 content cache key
includes it (FR-1.5b-7.5) — changing feedback decisions invalidates only
the affected template's cache.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.embeddings.api import Embedding, EmbeddingService
from src.embeddings.hash_embedder import HashEmbeddingService
from src.extraction.feedback_log import FeedbackEntry, FeedbackLog

# ----------------------------------------------------------------------
# Output model
# ----------------------------------------------------------------------


class ContextExample(BaseModel):
    """One positive example in the active context block."""

    model_config = ConfigDict(extra="forbid")

    pattern: str
    pattern_canonical: str
    decided_at: datetime
    selection_score: float
    feedback_id: str


class ContextBlocklistEntry(BaseModel):
    """One blocklist entry in the active context block."""

    model_config = ConfigDict(extra="forbid")

    pattern: str
    pattern_canonical: str
    last_decided_at: datetime
    hit_count: int
    feedback_id: str


class ContextBlock(BaseModel):
    """The full active context for a Pass-4 template + corpus pair."""

    model_config = ConfigDict(extra="forbid")

    corpus_id: str
    prompt_template_id: str
    examples: list[ContextExample] = Field(default_factory=list)
    blocklist: list[ContextBlocklistEntry] = Field(default_factory=list)
    context_hash: str
    feedback_log_count: int = 0

    def render_prompt_fragment(self) -> str:
        """Serialize examples + blocklist as a BAML-friendly text block."""

        lines: list[str] = []
        if self.examples:
            lines.append("# Previously accepted patterns:")
            for ex in self.examples:
                lines.append(f"- {ex.pattern}")
        if self.blocklist:
            lines.append("")
            lines.append("# Do NOT extract these (previously rejected):")
            for bl in self.blocklist:
                lines.append(f"- {bl.pattern}")
        return "\n".join(lines)


# ----------------------------------------------------------------------
# Scoring weights (operator-tunable per `/settings/feedback-loop`)
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class ActiveLearningWeights:
    """Hybrid-scoring weights for the top-K positive-example selection."""

    relevance: float = 0.4
    recency: float = 0.2
    diversity: float = 0.3
    frequency: float = 0.1
    half_life_days: float = 90.0
    min_diversity_distance: float = 0.15


# ----------------------------------------------------------------------
# The loader
# ----------------------------------------------------------------------


@dataclass
class FeedbackContextLoader:
    """Build a `ContextBlock` for one (corpus, template) pair."""

    feedback_log: FeedbackLog
    embedding_service: EmbeddingService = field(
        default_factory=HashEmbeddingService,
    )
    weights: ActiveLearningWeights = field(
        default_factory=ActiveLearningWeights,
    )

    # ADR-018 hard caps (NOT operator-tunable).
    POSITIVE_K: int = 4
    BLOCKLIST_CAP: int = 50

    def build(
        self,
        *,
        corpus_id: str,
        prompt_template_id: str,
    ) -> ContextBlock:
        # Layer 1: load everything for this corpus + template.
        positives = self.feedback_log.list_for_corpus(
            corpus_id, verdict="accept",
            prompt_template_id=prompt_template_id,
        )
        rejects = self.feedback_log.list_for_corpus(
            corpus_id, verdict="reject",
            prompt_template_id=prompt_template_id,
        )
        total = self.feedback_log.count(corpus_id)

        # Layer 2: select top-K positives via hybrid scoring.
        template_embedding = self.embedding_service.embed(
            f"template:{prompt_template_id}",
        )
        examples = self._select_top_k_positive(
            positives, template_embedding=template_embedding,
        )

        # Layer 2b: select ≤ 50 blocklist entries via LFU+LRU.
        blocklist = self._select_blocklist(rejects)

        block = ContextBlock(
            corpus_id=corpus_id,
            prompt_template_id=prompt_template_id,
            examples=examples,
            blocklist=blocklist,
            context_hash="",  # filled below
            feedback_log_count=total,
        )
        block.context_hash = _hash_context(block)
        return block

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def _select_top_k_positive(
        self,
        positives: list[FeedbackEntry],
        *,
        template_embedding: Embedding,
    ) -> list[ContextExample]:
        if not positives:
            return []

        now = datetime.now(UTC)
        # Pre-compute embedding + frequency.
        pattern_freq: dict[str, int] = {}
        for entry in positives:
            pattern_freq[entry.pattern_canonical] = (
                pattern_freq.get(entry.pattern_canonical, 0) + 1
            )
        max_freq = max(pattern_freq.values()) if pattern_freq else 1

        scored: list[tuple[FeedbackEntry, Embedding, float]] = []
        for entry in positives:
            emb = self.embedding_service.embed(entry.pattern)
            relevance = max(0.0, _cosine(emb, template_embedding))
            age_days = (now - entry.decided_at).total_seconds() / 86400
            recency = math.exp(-age_days / self.weights.half_life_days)
            freq = pattern_freq[entry.pattern_canonical] / max_freq
            base_score = (
                self.weights.relevance * relevance
                + self.weights.recency * recency
                + self.weights.frequency * freq
            )
            scored.append((entry, emb, base_score))

        # Greedy top-K with diversity constraint.
        scored.sort(key=lambda t: t[2], reverse=True)
        selected: list[tuple[FeedbackEntry, Embedding, float]] = []
        for cand_entry, cand_emb, cand_score in scored:
            if len(selected) >= self.POSITIVE_K:
                break
            min_dist = (
                min(
                    1.0 - _cosine(cand_emb, sel_emb)
                    for _, sel_emb, _ in selected
                )
                if selected else 1.0
            )
            if (
                selected
                and min_dist < self.weights.min_diversity_distance
            ):
                continue
            div_bonus = self.weights.diversity * min(min_dist, 1.0)
            selected.append((cand_entry, cand_emb, cand_score + div_bonus))

        return [
            ContextExample(
                pattern=entry.pattern,
                pattern_canonical=entry.pattern_canonical,
                decided_at=entry.decided_at,
                selection_score=score,
                feedback_id=entry.feedback_id,
            )
            for entry, _, score in selected
        ]

    def _select_blocklist(
        self, rejects: list[FeedbackEntry],
    ) -> list[ContextBlocklistEntry]:
        if not rejects:
            return []

        # Hit-count + last-seen-at per canonical pattern.
        by_canonical: dict[str, list[FeedbackEntry]] = {}
        for entry in rejects:
            by_canonical.setdefault(entry.pattern_canonical, []).append(entry)

        condensed: list[ContextBlocklistEntry] = []
        for canonical, entries in by_canonical.items():
            entries.sort(key=lambda e: e.decided_at, reverse=True)
            latest = entries[0]
            condensed.append(ContextBlocklistEntry(
                pattern=latest.pattern,
                pattern_canonical=canonical,
                last_decided_at=latest.decided_at,
                hit_count=len(entries),
                feedback_id=latest.feedback_id,
            ))

        if len(condensed) <= self.BLOCKLIST_CAP:
            return sorted(
                condensed, key=lambda e: e.last_decided_at, reverse=True,
            )

        # LFU+LRU eviction — sort by composite "keep score" (hit-frequency
        # primary, recency secondary).
        now = datetime.now(UTC)

        def _keep_score(entry: ContextBlocklistEntry) -> float:
            age_days = (now - entry.last_decided_at).total_seconds() / 86400
            recency = math.exp(-age_days / self.weights.half_life_days)
            freq = entry.hit_count
            return 0.7 * freq + 0.3 * recency

        condensed.sort(key=_keep_score, reverse=True)
        return condensed[: self.BLOCKLIST_CAP]


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _cosine(a: Embedding, b: Embedding) -> float:
    if len(a.vector) != len(b.vector):
        return 0.0
    dot = sum(x * y for x, y in zip(a.vector, b.vector, strict=True))
    na = math.sqrt(sum(x * x for x in a.vector))
    nb = math.sqrt(sum(x * x for x in b.vector))
    if na == 0 or nb == 0:
        return 0.0
    return float(dot / (na * nb))


def _hash_context(block: ContextBlock) -> str:
    """Deterministic hash of the block contents (FR-1.5b-7.5)."""

    canonical: dict[str, Any] = {
        "corpus_id": block.corpus_id,
        "prompt_template_id": block.prompt_template_id,
        "examples": [
            (e.pattern_canonical, e.feedback_id)
            for e in block.examples
        ],
        "blocklist": [
            (b.pattern_canonical, b.feedback_id)
            for b in block.blocklist
        ],
    }
    serialized = json.dumps(canonical, sort_keys=True).encode("utf-8")
    return sha256(serialized).hexdigest()[:16]


__all__ = [
    "ActiveLearningWeights",
    "ContextBlock",
    "ContextBlocklistEntry",
    "ContextExample",
    "FeedbackContextLoader",
]
