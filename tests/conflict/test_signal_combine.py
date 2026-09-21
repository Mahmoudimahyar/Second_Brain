"""Tests for V1.5c Phase 2 — 3-signal majority combine (ADR-016 v2)."""

from __future__ import annotations

from src.conflict.signal_combine import (
    CONFIDENCE_FLOOR,
    SignalInput,
    combine_signals,
)


def _sig(verdict: str, conf: float = 0.8) -> SignalInput:
    return SignalInput(
        label="t", verdict=verdict, confidence=conf,  # type: ignore[arg-type]
    )


def test_all_three_supports_writes_verdict() -> None:
    out = combine_signals([
        _sig("supports", 0.9), _sig("supports", 0.85), _sig("supports", 0.8),
    ])
    assert out.outcome == "supports"
    assert out.confidence >= CONFIDENCE_FLOOR
    assert not out.low_confidence


def test_two_of_three_supports_writes_with_low_confidence_flag() -> None:
    out = combine_signals([
        _sig("supports", 0.9), _sig("supports", 0.8), _sig("refutes", 0.7),
    ])
    assert out.outcome == "supports"
    assert out.low_confidence is True


def test_two_of_three_refutes_writes_refutes() -> None:
    out = combine_signals([
        _sig("refutes", 0.9), _sig("refutes", 0.8), _sig("supports", 0.7),
    ])
    assert out.outcome == "refutes"


def test_all_unknown_returns_unknown_research_need() -> None:
    out = combine_signals([
        _sig("unknown", 0.1), _sig("unknown", 0.0), _sig("unknown", 0.0),
    ])
    assert out.outcome == "unknown"
    assert not out.low_confidence


def test_below_confidence_floor_routes_disagreement() -> None:
    out = combine_signals([
        _sig("supports", 0.4), _sig("supports", 0.3), _sig("refutes", 0.5),
    ])
    assert out.outcome == "disagreement"
    assert out.low_confidence


def test_one_actionable_routes_disagreement() -> None:
    out = combine_signals([
        _sig("supports", 0.95), _sig("unknown", 0.0), _sig("unknown", 0.0),
    ])
    assert out.outcome == "disagreement"
    assert "fewer than 2" in out.reason


def test_wrong_input_count_disagrees() -> None:
    out = combine_signals([_sig("supports", 0.9), _sig("supports", 0.8)])
    assert out.outcome == "disagreement"
    assert "expected 3 signals" in out.reason
