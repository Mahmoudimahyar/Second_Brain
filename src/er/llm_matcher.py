"""LLM-matcher fallback for the low-confidence ER band (ADR-022, GAP-044).

DITTO/rapidfuzz handle the easy majority; the ambiguous tail (the
`needs_review` band, ~75-90 rapidfuzz) benefits from an LLM matcher
(Peeters & Bizer 2023: LLM matchers beat fine-tuned PLMs on the hard tail).
Auto-accept high / reject low / **LLM the middle** — concentrating LLM spend on
the few % of hard aliases. All calls go through `src/gateway/` (non-negotiable #9).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

from src.gateway.api import ModelGateway, TaskID, strip_json_fences


class MentionLLMMatcher(Protocol):
    """Resolve a borderline mention: True=accept, False=reject, None=undecided
    (keep for HITL)."""

    def resolve(self, text: str, canonical_name: str) -> bool | None: ...


class _MatchAnswer(BaseModel):
    is_match: bool = False
    reasoning: str = ""


@dataclass(frozen=True)
class GatewayLLMMatcher:
    """Gateway-routed LLM matcher (cheap tier first per ADR-023)."""

    gateway: ModelGateway
    task: TaskID = TaskID.ENTITY_MATCH_HARD

    def resolve(self, text: str, canonical_name: str) -> bool | None:
        prompt = (
            "Decide whether the text genuinely refers to this U.S. dental "
            f"school: {canonical_name!r}.\n\nText: {text!r}\n\n"
            'Respond with JSON only: {"is_match": true/false, "reasoning": "..."}. '
            "Answer false for coincidental substrings, metaphors, or a different school."
        )
        try:
            resp = self.gateway.complete(
                self.task, prompt, schema=_MatchAnswer,
                cache_key=f"er_match:{canonical_name}",
            )
        except Exception:
            return None  # gateway unavailable → undecided → keep for HITL
        if isinstance(resp.output, _MatchAnswer):
            return resp.output.is_match
        raw = strip_json_fences(resp.raw_text or "")
        try:
            return _MatchAnswer.model_validate_json(raw).is_match
        except ValueError:
            return None
