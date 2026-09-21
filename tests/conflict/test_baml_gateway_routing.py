"""W1-1 — tests that the V1.5c BAML templates route through the gateway in
production and raise loudly when the offline heuristic is invoked without
``SECBRAIN_OFFLINE=1``.

This is the failing-first test that locks in the ADR-016 v2 + ADR-011
invariant. The prior session shipped the heuristic Python fallbacks as
the production code path; this test fails until production functions
exist that go through ``default_gateway()`` and the heuristic functions
refuse to run unless explicitly opted in via the env var.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.conflict.baml.templates import (
    VerifyResult,
    heuristic_make_question,
    heuristic_paraphrase,
    heuristic_verify_claim,
    make_question_via_gateway,
    paraphrase_via_gateway,
    verify_claim_via_gateway,
)
from src.gateway.api import (
    GatewayResponse,
    ModelGateway,
    TaskID,
)


def _stub_gateway_response(text: str) -> GatewayResponse:
    return GatewayResponse(
        vendor="mock",
        model="mock-v1",
        output=None,
        raw_text=text,
        input_tokens=10,
        output_tokens=10,
        cached_input_tokens=0,
        cost_usd=0.0,
        latency_ms=1.0,
        cache_hit=False,
        audit_id="audit:test",
    )


# ---------------------------------------------------------------------
# Production-path tests: must invoke default_gateway()
# ---------------------------------------------------------------------


def test_make_question_via_gateway_invokes_gateway_with_correct_task() -> None:
    """Production path: make_question routes through gateway TaskID."""

    gw = MagicMock(spec=ModelGateway)
    gw.complete.return_value = _stub_gateway_response("What is the tuition at NYU?")

    result = make_question_via_gateway(
        "NYU dental tuition is $87000",
        gateway=gw,
    )

    assert result == "What is the tuition at NYU?"
    gw.complete.assert_called_once()
    call_args = gw.complete.call_args
    assert call_args.args[0] == TaskID.WEB_VERIFY_MAKE_QUESTION


def test_paraphrase_via_gateway_invokes_gateway_with_correct_task() -> None:
    """Production path: paraphrase routes through gateway TaskID."""

    gw = MagicMock(spec=ModelGateway)
    gw.complete.return_value = _stub_gateway_response(
        "How much does NYU dental school cost?",
    )

    result = paraphrase_via_gateway(
        "What is the tuition at NYU?",
        gateway=gw,
    )

    assert result == "How much does NYU dental school cost?"
    gw.complete.assert_called_once()
    call_args = gw.complete.call_args
    assert call_args.args[0] == TaskID.WEB_VERIFY_PARAPHRASE


def test_verify_claim_via_gateway_haiku_task() -> None:
    """Production path: verify_claim haiku variant routes through Haiku task."""

    gw = MagicMock(spec=ModelGateway)
    gw.complete.return_value = _stub_gateway_response(
        '{"verdict": "supports", "evidence_excerpt": "tuition is $87,000", '
        '"confidence": 0.9}',
    )

    result = verify_claim_via_gateway(
        claim="NYU dental tuition is $87000",
        evidence="NYU College of Dentistry tuition $87,000 for 2024-25.",
        task=TaskID.WEB_VERIFY_CLAIM_HAIKU,
        gateway=gw,
    )

    assert isinstance(result, VerifyResult)
    assert result.verdict == "supports"
    assert result.confidence == 0.9
    gw.complete.assert_called_once()
    assert gw.complete.call_args.args[0] == TaskID.WEB_VERIFY_CLAIM_HAIKU


def test_verify_claim_via_gateway_gemini_task() -> None:
    """Production path: verify_claim gemini variant routes through Gemini task."""

    gw = MagicMock(spec=ModelGateway)
    gw.complete.return_value = _stub_gateway_response(
        '{"verdict": "refutes", "evidence_excerpt": "Los Angeles, not San Francisco", '
        '"confidence": 0.95}',
    )

    result = verify_claim_via_gateway(
        claim="UCLA dental school is in San Francisco",
        evidence="UCLA School of Dentistry, Los Angeles campus.",
        task=TaskID.WEB_VERIFY_CLAIM_GEMINI,
        gateway=gw,
    )

    assert result.verdict == "refutes"
    assert gw.complete.call_args.args[0] == TaskID.WEB_VERIFY_CLAIM_GEMINI


def test_verify_claim_via_gateway_handles_malformed_json_as_unknown() -> None:
    """Robustness: garbled gateway output → ``unknown`` (never raises)."""

    gw = MagicMock(spec=ModelGateway)
    gw.complete.return_value = _stub_gateway_response("not valid json")

    result = verify_claim_via_gateway(
        claim="anything",
        evidence="anything",
        task=TaskID.WEB_VERIFY_CLAIM_HAIKU,
        gateway=gw,
    )
    assert result.verdict == "unknown"


# ---------------------------------------------------------------------
# Offline-mode tests: heuristic_* raise RuntimeError unless SECBRAIN_OFFLINE=1
# ---------------------------------------------------------------------


def test_heuristic_make_question_raises_without_offline_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SECBRAIN_OFFLINE", raising=False)
    with pytest.raises(RuntimeError, match="SECBRAIN_OFFLINE"):
        heuristic_make_question("a claim")


def test_heuristic_paraphrase_raises_without_offline_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SECBRAIN_OFFLINE", raising=False)
    with pytest.raises(RuntimeError, match="SECBRAIN_OFFLINE"):
        heuristic_paraphrase("a question")


def test_heuristic_verify_claim_raises_without_offline_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SECBRAIN_OFFLINE", raising=False)
    with pytest.raises(RuntimeError, match="SECBRAIN_OFFLINE"):
        heuristic_verify_claim("a claim", "evidence")


def test_heuristic_make_question_works_when_offline_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SECBRAIN_OFFLINE", "1")
    result = heuristic_make_question("NYU tuition is $87000")
    assert "?" in result


def test_heuristic_paraphrase_works_when_offline_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SECBRAIN_OFFLINE", "1")
    out = heuristic_paraphrase("What is the tuition?")
    assert out


def test_heuristic_verify_claim_works_when_offline_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SECBRAIN_OFFLINE", "1")
    out = heuristic_verify_claim(
        "NYU tuition is $87000",
        "NYU tuition for 2024-25 was $87,000",
    )
    assert out.verdict in {"supports", "unknown", "refutes"}


# ---------------------------------------------------------------------
# WebVerificationAgent defaults — production wiring
# ---------------------------------------------------------------------


def test_web_verification_agent_defaults_use_gateway_not_heuristic() -> None:
    """The default WebVerificationAgent must not call heuristic_*.

    Post-W1-2: ``verify`` (legacy single-vendor) defaults to None and
    ``verify_two_vendor`` defaults to the two-vendor gateway wrapper.
    """

    from src.conflict.providers.tavily import TavilyProvider  # noqa: PLC0415
    from src.conflict.web_verify import WebVerificationAgent  # noqa: PLC0415

    agent = WebVerificationAgent(
        provider=TavilyProvider(api_key="placeholder-not-used"),
    )

    # make_question and paraphrase invoke gateway functions, not heuristics.
    assert agent.make_question.invoke is not heuristic_make_question
    assert agent.paraphrase.invoke is not heuristic_paraphrase

    # Legacy single-vendor verify is None by default; two-vendor wrapper
    # is the production path.
    assert agent.verify is None
    assert agent.verify_two_vendor is not None
    invoke_name = getattr(agent.verify_two_vendor, "__name__", "")
    assert "two_vendor" in invoke_name, (
        f"verify_two_vendor should be the two-vendor gateway wrapper, got {invoke_name!r}"
    )


# ---------------------------------------------------------------------
# Smoke — gateway has the new TaskID slots registered
# ---------------------------------------------------------------------


def test_taskid_enum_includes_v15c_web_verify_slots() -> None:
    """ADR-016 v2 + tech-stack matrix lock in 4 new TaskID slots for V1.5c."""

    assert hasattr(TaskID, "WEB_VERIFY_MAKE_QUESTION")
    assert hasattr(TaskID, "WEB_VERIFY_PARAPHRASE")
    assert hasattr(TaskID, "WEB_VERIFY_CLAIM_HAIKU")
    assert hasattr(TaskID, "WEB_VERIFY_CLAIM_GEMINI")
    assert hasattr(TaskID, "TEAM_CONTENT_ANGLES")


def test_default_gateway_registers_v15c_slots_when_keys_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """default_gateway() must register the new V1.5c task slots when
    GEMINI/ANTHROPIC keys are present."""

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from src.gateway.api import default_gateway  # noqa: PLC0415

    gw = default_gateway()
    # Both vendors present → both verify-claim slots registered.
    assert TaskID.WEB_VERIFY_MAKE_QUESTION in gw.task_to_client
    assert TaskID.WEB_VERIFY_PARAPHRASE in gw.task_to_client
    assert TaskID.WEB_VERIFY_CLAIM_HAIKU in gw.task_to_client
    assert TaskID.WEB_VERIFY_CLAIM_GEMINI in gw.task_to_client
    assert TaskID.TEAM_CONTENT_ANGLES in gw.task_to_client


_ = Any  # silence unused-import warning
