"""Cross-vendor LLM-as-judge for same-tier same-year ties per ADR-006.

Restricted to: same `source_tier`, same `t_valid_*` window, equal `credibility`.
Anything broader stays out of LLM-as-judge per ADR-006 (avoiding systemic
single-LLM bias on factual recall).

V1 contract:
  - Three vendors vote: Anthropic + OpenAI + Gemini (per ADR-011 keys).
  - Each vendor returns a single winning `claim_id` or null.
  - 2/3 (or 3/3) agreement → that claim wins.
  - 1/1/1 split → resolver escalates to HITL with the transcript.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel

from src.gateway.api import TaskID, strip_json_fences

if TYPE_CHECKING:  # avoid circular import; only types used in annotations
    from src.conflict.resolver import Claim
    from src.gateway.api import LLMClient


def _family_of(vendor: str | None) -> str:
    """Normalize a vendor / extractor string to its model family (ADR-024)."""
    v = (vendor or "").strip().lower()
    if v in {"gemini", "google", "google-genai", "vertex"}:
        return "google"
    if v in {"grok", "xai"}:
        return "xai"
    return v


@dataclass(frozen=True)
class JudgeVote:
    """Outcome of one adjudication round."""

    winner_claim_id: str | None
    per_vendor: dict[str, str | None]   # {vendor: predicted_winner_or_None}
    agreement: int                       # number of vendors agreeing on majority pick
    transcript: str = ""                 # human-readable reasoning for the audit log


class _JudgeAnswer(BaseModel):
    """Vendor schema; tolerant of extra fields."""

    winner_claim_id: str | None = None
    reasoning: str = ""


class LLMJudge(Protocol):
    def adjudicate(
        self, new_claim: Claim, candidates: list[Claim],
    ) -> JudgeVote: ...


@dataclass(frozen=True)
class StubJudge:
    """Test seam: returns a fixed JudgeVote regardless of inputs."""

    vote: JudgeVote

    def adjudicate(
        self, new_claim: Claim, candidates: list[Claim],
    ) -> JudgeVote:
        _ = new_claim, candidates
        return self.vote


@dataclass
class ThreeVendorJudge:
    """3-vendor majority judge. Per ADR-006 + ADR-011.

    `clients` is exactly 3 `LLMClient` instances (one Anthropic + one OpenAI +
    one Gemini in production). Tests pass 3 `MockProvider` instances.

    The prompt asks for strict JSON: `{"winner_claim_id": "...", "reasoning": "..."}`.
    Schemas are pydantic-validated; missing/malformed responses count as a null vote.
    """

    clients: list[LLMClient] = field(default_factory=list)
    minimum_agreement: int = 2          # 2/3 default; 3/3 if caller wants stricter

    def __post_init__(self) -> None:
        families = {_family_of(c.vendor) for c in self.clients}
        if len(self.clients) < 3 or len(families) < 3:
            raise ValueError(
                "ThreeVendorJudge needs a pool of >=3 clients spanning >=3 "
                f"distinct vendor families; got {len(self.clients)} clients / "
                f"{len(families)} families.",
            )

    def _select_panel(self, claims: list[Claim]) -> list[LLMClient]:
        """ADR-024 family-exclusion: a 3-family panel excluding the vendor family
        that produced any candidate's extraction. Substitutes an alternate family
        when the pool has one; otherwise keeps 3 (best effort, recorded in the
        transcript). One client per family."""

        excluded = {_family_of(c.extractor_family) for c in claims if c.extractor_family}
        by_family: dict[str, LLMClient] = {}
        for client in self.clients:
            by_family.setdefault(_family_of(client.vendor), client)
        preferred = [cl for fam, cl in by_family.items() if fam not in excluded]
        fallback = [cl for fam, cl in by_family.items() if fam in excluded]
        return (preferred + fallback)[:3]

    def adjudicate(
        self, new_claim: Claim, candidates: list[Claim],
    ) -> JudgeVote:
        all_claims = [new_claim, *candidates]
        panel = self._select_panel(all_claims)
        excluded = {_family_of(c.extractor_family) for c in all_claims if c.extractor_family}
        prompt = self._build_prompt(new_claim, candidates)
        per_vendor: dict[str, str | None] = {}
        reasonings: list[str] = []
        for client in panel:  # independent vote — no judge sees another's verdict
            answer = self._ask(client, prompt)
            per_vendor[client.vendor] = answer.winner_claim_id
            if answer.reasoning:
                reasonings.append(f"[{client.vendor}] {answer.reasoning}")

        panel_note = (
            f"panel={[c.vendor for c in panel]} excluded_families={sorted(excluded)}"
        )
        transcript = panel_note + ((" || " + " | ".join(reasonings)) if reasonings else "")

        # Tally — None votes are ignored for majority detection.
        valid_votes = [v for v in per_vendor.values() if v is not None]
        if not valid_votes:
            return JudgeVote(
                winner_claim_id=None, per_vendor=per_vendor,
                agreement=0, transcript=transcript,
            )
        counts = Counter(valid_votes)
        winner, top_count = counts.most_common(1)[0]
        winner_id: str | None = winner if top_count >= self.minimum_agreement else None
        return JudgeVote(
            winner_claim_id=winner_id, per_vendor=per_vendor,
            agreement=top_count, transcript=transcript,
        )

    @staticmethod
    def _build_prompt(new_claim: Claim, candidates: list[Claim]) -> str:
        claim_lines: list[str] = []
        for c in [new_claim, *candidates]:
            claim_lines.append(
                f"- claim_id={c.claim_id} subject={c.subject_id} "
                f"predicate={c.predicate} value={c.object_value!r} "
                f"tier={c.source_tier} credibility={c.credibility:.2f} "
                f"refs={c.references}",
            )
        return (
            "You are an impartial judge. The following claims about the same "
            "(subject, predicate) at the same trust tier and time window are in "
            "conflict. Pick the single most credible `claim_id`, or return null "
            "if the evidence is insufficient.\n\n"
            + "\n".join(claim_lines) + "\n\n"
            'Respond with JSON only: {"winner_claim_id": "...", "reasoning": "..."}.'
        )

    @staticmethod
    def _ask(client: LLMClient, prompt: str) -> _JudgeAnswer:
        try:
            response = client.complete(
                prompt, schema=_JudgeAnswer,
                cache_key=f"judge:{TaskID.JUDGE_TIE_BREAK.value}",
            )
        except Exception:
            return _JudgeAnswer()
        if isinstance(response.output, _JudgeAnswer):
            return response.output
        # Fall back to text parse — vendors that don't return parsed schemas.
        raw = strip_json_fences(response.raw_text or "")
        try:
            return _JudgeAnswer.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValueError):
            return _JudgeAnswer()
