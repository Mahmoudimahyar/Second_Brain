"""V1.5a Phase 5 — `CrossGraphLinker` (FR-1.5a-5, ADR-015).

Reuses V1's alias-resolution stack (rapidfuzz token_set_ratio + BGE-small
embeddings) in cross-source mode. The Pass 1 mention-extraction front-end
is bypassed — inputs are already structured `CrossGraphEntity` objects.

Confidence thresholds (FR-1.5a-5.2):
  ≥ 0.90 → SAME_AS edge written (routing='auto')
  0.75 ≤ x < 0.90 → cross_graph_link HITL item (routing='hitl')
  < 0.75 → no link (routing='reject')

SAME_AS storage convention (ADR-015 + data.md):
  - Single edge (canonical-ordered by node-id).
  - subject_tier + object_tier preserved per-endpoint.
  - bitemporal 4-tuple.
  - `references` cites both side's source rows / posts.
  - Tier promotion forbidden — neither endpoint changes tier from the edge.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from rapidfuzz import fuzz

from src.embeddings.api import Embedding, EmbeddingService
from src.ingestion.sources.base import SourceTier
from src.shared.timestamps import utc_now

# ----------------------------------------------------------------------
# Types
# ----------------------------------------------------------------------


CrossGraphLinkRouting = Literal["auto", "hitl", "reject"]


@dataclass(frozen=True)
class CrossGraphEntity:
    """A structured entity from one source, fed into the linker."""

    entity_id: str
    entity_type: str               # e.g., "School", "Program", "User"
    name: str
    aliases: tuple[str, ...] = ()
    tier: SourceTier = "L2"
    source_id: str = ""


class CrossGraphCandidate(BaseModel):
    """One pair-wise link candidate returned by the linker."""

    model_config = ConfigDict(extra="forbid")

    source_entity_id: str
    target_entity_id: str
    confidence: float
    routing: CrossGraphLinkRouting
    matched_signals: tuple[str, ...] = ()       # ("lexical", "embedding")
    evidence: dict[str, Any] = Field(default_factory=dict)


class SameAsEdge(BaseModel):
    """Persistent SAME_AS edge per data.md §SAME_AS table."""

    model_config = ConfigDict(extra="forbid")

    subject_id: str
    object_id: str
    subject_tier: SourceTier
    object_tier: SourceTier
    rank: Literal["preferred", "normal", "deprecated"]
    confidence: float
    references: tuple[str, ...]
    qualifiers: dict[str, Any] = Field(default_factory=dict)
    t_valid_from: datetime
    t_valid_to: datetime | None
    t_ingest_from: datetime
    t_ingest_to: datetime | None
    status: Literal["active", "superseded", "hitl_pending", "hitl_committed"]


# ----------------------------------------------------------------------
# The linker
# ----------------------------------------------------------------------


@dataclass
class CrossGraphLinker:
    """Cross-source entity linker.

    Reuses V1's two complementary signals:
      - Lexical: `rapidfuzz.token_set_ratio` on (name + aliases).
      - Embedding: BGE-small cosine on name strings.

    The two signals are blended into a single confidence. Strong lexical
    agreement (≥ 0.95) auto-wins regardless of embedding noise; otherwise
    the two are weighted.
    """

    embedding_service: EmbeddingService
    auto_threshold: float = 0.90
    hitl_threshold: float = 0.75

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def link(
        self,
        new_entity: CrossGraphEntity,
        universe: Iterable[CrossGraphEntity],
        *,
        top_k: int = 10,
    ) -> list[CrossGraphCandidate]:
        """Return top-K candidates for `new_entity` against `universe`.

        Filters by `entity_type` first — cross-type matches are rejected.
        Candidates with confidence < hitl_threshold are dropped from the
        return value.
        """

        candidates: list[CrossGraphCandidate] = []
        for cand_entity in universe:
            if cand_entity.entity_type != new_entity.entity_type:
                continue
            if cand_entity.entity_id == new_entity.entity_id:
                continue
            score, signals, evidence = self._score_pair(new_entity, cand_entity)
            if score < self.hitl_threshold:
                continue
            routing = _route(score, self.auto_threshold, self.hitl_threshold)
            candidates.append(CrossGraphCandidate(
                source_entity_id=new_entity.entity_id,
                target_entity_id=cand_entity.entity_id,
                confidence=score,
                routing=routing,
                matched_signals=tuple(signals),
                evidence=evidence,
            ))
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        return candidates[:top_k]

    def materialize_edge(
        self,
        a: CrossGraphEntity,
        b: CrossGraphEntity,
        *,
        confidence: float,
        status: Literal[
            "active", "hitl_pending", "hitl_committed",
        ] = "active",
        rank: Literal["preferred", "normal", "deprecated"] = "normal",
        qualifiers: dict[str, Any] | None = None,
        valid_from: datetime | None = None,
    ) -> SameAsEdge:
        """Produce a SAME_AS edge with canonical-ordering by entity_id.

        ADR-015: tier-per-endpoint is preserved; cross-graph SAME_AS never
        elevates an L2/L5 entity to L1. `confidence` ∈ [0, 1].
        """

        if a.entity_id <= b.entity_id:
            subj, obj = a, b
        else:
            subj, obj = b, a
        now = utc_now()
        return SameAsEdge(
            subject_id=subj.entity_id,
            object_id=obj.entity_id,
            subject_tier=subj.tier,
            object_tier=obj.tier,
            rank=rank,
            confidence=confidence,
            references=tuple(sorted({s for s in (a.source_id, b.source_id) if s})),
            qualifiers=qualifiers or {},
            t_valid_from=valid_from or now,
            t_valid_to=None,
            t_ingest_from=now,
            t_ingest_to=None,
            status=status,
        )

    # ------------------------------------------------------------------
    # Scoring internals
    # ------------------------------------------------------------------

    def _score_pair(
        self, a: CrossGraphEntity, b: CrossGraphEntity,
    ) -> tuple[float, list[str], dict[str, Any]]:
        """Return (score, signals, evidence) for one entity pair."""

        a_strings = [a.name, *a.aliases]
        b_strings = [b.name, *b.aliases]

        # Lexical: max token_set_ratio across all alias pairs
        best_lex = 0.0
        best_pair: tuple[str, str] | None = None
        for x in a_strings:
            for y in b_strings:
                ratio = fuzz.token_set_ratio(x.lower(), y.lower()) / 100.0
                if ratio > best_lex:
                    best_lex = ratio
                    best_pair = (x, y)

        # Embedding signal — only on canonical names (not aliases) to keep
        # the cost bounded.
        emb_a = self.embedding_service.embed(a.name)
        emb_b = self.embedding_service.embed(b.name)
        emb_score = _cosine(emb_a, emb_b)
        emb_score = max(0.0, emb_score)

        signals: list[str] = []
        if best_lex >= 0.80:
            signals.append("lexical")
        if emb_score >= 0.60:
            signals.append("embedding")

        # Blend strategy:
        #   - Lexical ≥ 0.95 → auto-win (catches exact alias matches).
        #   - Otherwise: take the MAX of (lexical alone) and (weighted blend).
        #     Strong lexical never gets discounted by a weak embedding signal
        #     (which is common when names are synonymous but lexically
        #     different — e.g., "HSDM" vs "Harvard School of Dental Medicine"
        #     where embedding similarity is moderate but lexical is decisive
        #     via alias overlap).
        if best_lex >= 0.95:
            score = best_lex
        else:
            blended = 0.7 * best_lex + 0.3 * emb_score
            score = max(best_lex * 0.95, blended)  # 5% lex-only discount

        # Domain-disambiguation penalty: dental schools vs medical schools
        # share many lexical tokens but are semantically distinct entities.
        # Detect via domain-keyword presence and penalize cross-domain matches.
        domain_a = _domain_of(a.name)
        domain_b = _domain_of(b.name)
        cross_domain = (
            domain_a is not None and domain_b is not None
            and domain_a != domain_b
        )
        if cross_domain:
            score *= 0.7
            signals.append("cross_domain_penalty")

        evidence: dict[str, Any] = {
            "lexical_score": round(best_lex, 4),
            "embedding_score": round(emb_score, 4),
            "best_lex_pair": list(best_pair) if best_pair else None,
            "domain_a": domain_a,
            "domain_b": domain_b,
            "cross_domain": cross_domain,
        }
        return score, signals, evidence


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


_DENTAL_KEYWORDS: frozenset[str] = frozenset({
    "dental", "dentistry", "dent", "dmd", "dds", "stomatology",
})
_MEDICAL_KEYWORDS: frozenset[str] = frozenset({
    "medical", "medicine", "med",  # NOTE: "med" must be word-bounded
})
_LAW_KEYWORDS: frozenset[str] = frozenset({"law", "jurisprudence"})
_BUSINESS_KEYWORDS: frozenset[str] = frozenset({
    "business", "management", "mba",
})


def _domain_of(name: str) -> str | None:
    """Best-effort domain inference from a school's name.

    Returns 'dental' | 'medical' | 'law' | 'business' | None. Dental wins
    over medical if both appear (e.g., "School of Dental Medicine" → dental).
    """

    tokens = {t.strip(",.()") for t in name.lower().split()}
    if tokens & _DENTAL_KEYWORDS:
        return "dental"
    if tokens & _MEDICAL_KEYWORDS:
        return "medical"
    if tokens & _LAW_KEYWORDS:
        return "law"
    if tokens & _BUSINESS_KEYWORDS:
        return "business"
    return None


def _cosine(a: Embedding, b: Embedding) -> float:
    if len(a.vector) != len(b.vector):
        return 0.0
    dot = sum(x * y for x, y in zip(a.vector, b.vector, strict=True))
    na = math.sqrt(sum(x * x for x in a.vector))
    nb = math.sqrt(sum(x * x for x in b.vector))
    if na == 0 or nb == 0:
        return 0.0
    return float(dot / (na * nb))


def _route(
    confidence: float, auto: float, hitl: float,
) -> CrossGraphLinkRouting:
    if confidence >= auto:
        return "auto"
    if confidence >= hitl:
        return "hitl"
    return "reject"


__all__ = [
    "CrossGraphCandidate",
    "CrossGraphEntity",
    "CrossGraphLinkRouting",
    "CrossGraphLinker",
    "SameAsEdge",
]
