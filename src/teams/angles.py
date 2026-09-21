"""V1.5c — `suggest_angles` (FR-1.5c-4 + ADR-016 v2).

Single entry-point that routes through the model gateway with task
`team_content_angles`. Per V1.5-R2 the default is Gemini 2.5 Flash-Lite,
swappable via per-task matrix without code change.

Every angle is a *draft* with a "Draft only" watermark per ADR-016 v2.
Never auto-published.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Team = Literal["pm", "social", "marketing"]


class SuggestedAngle(BaseModel):
    """One LLM-generated angle. Always 'draft only' per ADR-016 v2."""

    model_config = ConfigDict(extra="forbid")

    angle: str
    rationale: str = ""
    citations: list[str] = Field(default_factory=list)
    draft_only: bool = True


@dataclass
class AngleSuggester:
    """Suggester wrapping a single callable that hits the gateway.

    Production wires `default_gateway().complete(task=TaskID.TEAM_CONTENT_ANGLES, ...)`
    here. Tests inject a deterministic callable.
    """

    invoke: Callable[[Team, str, dict[str, object]], list[SuggestedAngle]]

    def __call__(
        self, team: Team, item_id: str, context: dict[str, object],
    ) -> list[SuggestedAngle]:
        return self.invoke(team, item_id, context)


def heuristic_angles(
    team: Team, item_id: str, context: dict[str, object],
) -> list[SuggestedAngle]:
    """Deterministic fallback for offline dev — produces 3 stub angles
    per team based on the context's `title` / `topic`. Production
    overrides with a real Gemini call via the gateway.
    """

    label = str(
        context.get("title")
        or context.get("topic")
        or context.get("name")
        or item_id,
    )
    refs_raw = context.get("references") or []
    refs_iter = refs_raw if isinstance(refs_raw, list | tuple) else []
    citations = [str(r) for r in refs_iter]
    seeds = {
        "pm": [
            f"Build a {label}-focused onboarding flow that surfaces concerns early.",
            f"Add a dedicated FAQ + comparison table addressing {label}.",
            f"Run a user-research session targeting {label} pain points.",
        ],
        "social": [
            f"Carousel post unpacking {label} myths vs facts.",
            f"Short-form video featuring a student's {label} experience.",
            f"Thread of evidence-backed answers on {label}.",
        ],
        "marketing": [
            f"Comprehensive guide page on {label} optimized for search.",
            f"Comparison hub: {label} options + tradeoffs.",
            f"Email nurture sequence covering {label} concerns over 5 days.",
        ],
    }[team]
    return [
        SuggestedAngle(
            angle=angle,
            rationale=f"Heuristic stub angle for {team} based on '{label}'.",
            citations=citations[:3],
            draft_only=True,
        )
        for angle in seeds
    ]


def suggest_angles(
    team: Team,
    item_id: str,
    context: dict[str, object],
    *,
    suggester: AngleSuggester | None = None,
    k: int = 3,
) -> list[SuggestedAngle]:
    """Public entry-point. Defaults to the deterministic heuristic; pass
    a custom `suggester` to wire the live gateway."""

    if suggester is None:
        suggester = AngleSuggester(invoke=heuristic_angles)
    return suggester(team, item_id, context)[:k]


__all__ = ["AngleSuggester", "SuggestedAngle", "Team", "heuristic_angles", "suggest_angles"]
