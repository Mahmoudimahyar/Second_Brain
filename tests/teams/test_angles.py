"""Tests for V1.5c `suggest_angles` (FR-1.5c-4, ADR-016 v2)."""

from __future__ import annotations

from src.teams.angles import AngleSuggester, SuggestedAngle, suggest_angles


def test_default_suggester_returns_three_angles() -> None:
    angles = suggest_angles(
        team="pm", item_id="pp:tuition:applicants",
        context={"title": "Tuition Anxiety", "references": ["post:1"]},
    )
    assert len(angles) == 3
    assert all(a.draft_only for a in angles)


def test_pm_angles_mention_label() -> None:
    angles = suggest_angles(
        team="pm", item_id="pp:dat",
        context={"title": "DAT Prep"},
    )
    assert any("DAT Prep" in a.angle for a in angles)


def test_social_angles_format() -> None:
    angles = suggest_angles(
        team="social", item_id="topic:nyu",
        context={"topic": "NYU Interviews"},
    )
    assert len(angles) == 3
    assert any("video" in a.angle.lower() for a in angles)


def test_marketing_angles_format() -> None:
    angles = suggest_angles(
        team="marketing", item_id="gap:tuition_compare",
        context={"name": "Tuition Comparison"},
    )
    assert len(angles) == 3
    assert any("comparison" in a.angle.lower() or "guide" in a.angle.lower()
               for a in angles)


def test_citations_propagate() -> None:
    angles = suggest_angles(
        team="pm", item_id="pp:1",
        context={"title": "X", "references": ["src:a", "src:b", "src:c", "src:d"]},
    )
    # Capped at 3 per heuristic; production gateway call honors the same.
    assert all(len(a.citations) <= 3 for a in angles)


def test_custom_suggester_injectable() -> None:
    def _custom(team: str, item_id: str, context: dict[str, object]) -> list[SuggestedAngle]:
        return [SuggestedAngle(angle=f"custom: {team}:{item_id}", draft_only=True)]

    angles = suggest_angles(
        team="pm",  # type: ignore[arg-type]
        item_id="x", context={},
        suggester=AngleSuggester(invoke=_custom),  # type: ignore[arg-type]
    )
    assert len(angles) == 1
    assert "custom" in angles[0].angle


def test_k_limit_applied() -> None:
    angles = suggest_angles(
        team="pm", item_id="x",
        context={"title": "Y"}, k=2,
    )
    assert len(angles) == 2


def test_draft_only_watermark_always_true() -> None:
    """ADR-016 v2: every output is draft-only, never auto-published."""
    for team in ("pm", "social", "marketing"):
        angles = suggest_angles(
            team=team,  # type: ignore[arg-type]
            item_id="x", context={"title": "Y"},
        )
        assert all(a.draft_only is True for a in angles)
