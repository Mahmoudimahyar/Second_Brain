"""V1.5c — 3-signal majority combine logic (ADR-016 v2).

Inputs: three independent verdict signals (A: Tavily QNA, B: Tavily search
on paraphrased question, C: two-vendor LLM extract-verify).

Outputs:
- `supports` / `refutes` when ≥ 2-of-3 agree with confidence ≥ 0.7.
- `disagreement` when no majority, with hint to escalate to HITL.
- `unknown` when all 3 signals return unknown — emits `research_need`.
- `low_confidence` flag when 2 agree but 3rd dissents.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from src.conflict.baml.templates import Verdict

CombineOutcome = Literal[
    "supports",
    "refutes",
    "disagreement",      # → HITL `web_search_disagreement`
    "unknown",           # → research_need
]


@dataclass(frozen=True)
class SignalInput:
    """One verdict signal."""

    label: str               # e.g., "tavily_qna", "tavily_paraphrase", "llm_verify"
    verdict: Verdict         # supports / refutes / unknown / disagreement
    confidence: float
    evidence_excerpt: str = ""


@dataclass(frozen=True)
class CombineResult:
    """Output of `combine_signals`."""

    outcome: CombineOutcome
    confidence: float
    low_confidence: bool     # True when 2-of-3 agree but 3rd dissents
    contributing: tuple[SignalInput, ...]
    reason: str


CONFIDENCE_FLOOR: float = 0.7


def combine_signals(signals: Sequence[SignalInput]) -> CombineResult:
    """Apply the 3-signal majority rule per ADR-016 v2."""

    if len(signals) != 3:
        return CombineResult(
            outcome="disagreement",
            confidence=0.0,
            low_confidence=True,
            contributing=tuple(signals),
            reason=f"expected 3 signals, got {len(signals)}",
        )

    # All-unknown → research_need.
    if all(s.verdict == "unknown" for s in signals):
        return CombineResult(
            outcome="unknown",
            confidence=0.0,
            low_confidence=False,
            contributing=tuple(signals),
            reason="all three signals returned unknown",
        )

    # Filter to non-disagreement signals; count actionable verdicts.
    actionable = [s for s in signals if s.verdict in {"supports", "refutes"}]
    if len(actionable) < 2:
        return CombineResult(
            outcome="disagreement",
            confidence=max((s.confidence for s in signals), default=0.0),
            low_confidence=True,
            contributing=tuple(signals),
            reason=(
                "fewer than 2 actionable signals; route to HITL "
                "web_search_disagreement"
            ),
        )

    # Tally per verdict.
    counts: dict[Verdict, list[SignalInput]] = {}
    for sig in actionable:
        counts.setdefault(sig.verdict, []).append(sig)

    # Best verdict + count.
    best_verdict, best_signals = max(
        counts.items(), key=lambda kv: (len(kv[1]), max(s.confidence for s in kv[1])),
    )
    best_count = len(best_signals)
    avg_conf = sum(s.confidence for s in best_signals) / max(best_count, 1)
    # ADR-016 v2: "≥ 2-of-3 agreement with confidence ≥ 0.7". Read as
    # "at least 2 of the agreeing signals are above the floor" rather
    # than "the average is above the floor" — a low-confidence
    # corroborator (e.g., signal C @ 0.3) should not veto a
    # high-confidence pair.
    above_floor = sum(
        1 for s in best_signals if s.confidence >= CONFIDENCE_FLOOR
    )

    if best_count >= 2 and above_floor >= 2:
        low_conf = best_count < len(actionable) or avg_conf < CONFIDENCE_FLOOR
        outcome: CombineOutcome = (
            "supports" if best_verdict == "supports" else "refutes"
        )
        return CombineResult(
            outcome=outcome,
            confidence=avg_conf,
            low_confidence=low_conf,
            contributing=tuple(best_signals),
            reason=(
                f"{best_count}-of-{len(actionable)} actionable signals agree "
                f"on {best_verdict} ({above_floor} above floor; "
                f"avg conf {avg_conf:.2f})"
            ),
        )

    return CombineResult(
        outcome="disagreement",
        confidence=avg_conf,
        low_confidence=True,
        contributing=tuple(signals),
        reason=(
            f"majority below confidence floor "
            f"(best {best_count}-of-{len(actionable)} @ {avg_conf:.2f})"
        ),
    )


__all__ = [
    "CONFIDENCE_FLOOR",
    "CombineOutcome",
    "CombineResult",
    "SignalInput",
    "combine_signals",
]
