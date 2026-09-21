"""Tests for `src.gateway.api.default_gateway` per-task routing (ADR-011)."""

from __future__ import annotations

import pytest

from src.gateway import TaskID, default_gateway


def test_default_gateway_registers_gemini_tasks_when_google_key_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "stub")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    gw = default_gateway()

    assert TaskID.PASS3_CLUSTER_SUMMARY in gw.task_to_client
    assert TaskID.PASS4_SENTIMENT in gw.task_to_client
    assert TaskID.HITL_SUMMARY in gw.task_to_client
    assert gw.task_to_client[TaskID.PASS3_CLUSTER_SUMMARY].vendor == "gemini"


def test_default_gateway_registers_anthropic_tasks_when_key_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "stub")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    gw = default_gateway()

    assert TaskID.PASS4_INTERVIEW_Q in gw.task_to_client
    assert TaskID.PASS4_CONFLICT_CANDIDATE in gw.task_to_client
    assert TaskID.PASS4_HARDEST in gw.task_to_client
    assert TaskID.JUDGE_TIE_BREAK in gw.task_to_client
    haiku = gw.task_to_client[TaskID.PASS4_INTERVIEW_Q]
    sonnet = gw.task_to_client[TaskID.PASS4_HARDEST]
    assert haiku.vendor == "anthropic"
    assert sonnet.vendor == "anthropic"
    assert "haiku" in haiku.model.lower()
    assert "sonnet" in sonnet.model.lower()


def test_default_gateway_recognizes_gemini_api_key_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "stub")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    gw = default_gateway()
    assert TaskID.PASS3_CLUSTER_SUMMARY in gw.task_to_client


def test_default_gateway_empty_when_no_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    gw = default_gateway()
    assert gw.task_to_client == {}


def test_default_gateway_falls_back_to_openai_when_anthropic_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GAP-046: OpenAI fills the Anthropic Pass-4 slots when Anthropic is missing."""

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "stub")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    gw = default_gateway()

    assert TaskID.PASS4_INTERVIEW_Q in gw.task_to_client
    assert TaskID.PASS4_CONFLICT_CANDIDATE in gw.task_to_client
    assert TaskID.PASS4_HARDEST in gw.task_to_client
    assert TaskID.JUDGE_TIE_BREAK in gw.task_to_client
    for task in (TaskID.PASS4_INTERVIEW_Q, TaskID.PASS4_CONFLICT_CANDIDATE,
                 TaskID.PASS4_HARDEST, TaskID.JUDGE_TIE_BREAK):
        assert gw.task_to_client[task].vendor == "openai"


def test_default_gateway_per_task_vendor_routing_when_both_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-003 matrix (refreshed 2026-05-30): interview-Q + hardest lead with the
    cheaper/stronger OpenAI model; conflict-candidate stays Anthropic-primary
    (precision); each keeps a cross-vendor fallback."""

    monkeypatch.setenv("ANTHROPIC_API_KEY", "stub")
    monkeypatch.setenv("OPENAI_API_KEY", "stub")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    gw = default_gateway()
    assert gw.task_to_client[TaskID.PASS4_INTERVIEW_Q].vendor == "openai"
    assert gw.task_to_client[TaskID.PASS4_HARDEST].vendor == "openai"
    assert gw.task_to_client[TaskID.PASS4_CONFLICT_CANDIDATE].vendor == "anthropic"


def test_default_gateway_raises_for_unregistered_task(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    gw = default_gateway()
    with pytest.raises(RuntimeError, match="No provider configured"):
        gw.complete(TaskID.PASS4_SENTIMENT, "p")
