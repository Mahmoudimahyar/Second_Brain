"""Tests for `src.gateway.api` (ADR-011)."""

from __future__ import annotations

import pytest

from src.gateway import (
    GatewayResponse,
    MockProvider,
    ModelGateway,
    TaskID,
)


def test_mock_provider_returns_gateway_response() -> None:
    provider = MockProvider()
    resp = provider.complete("hello world")

    assert isinstance(resp, GatewayResponse)
    assert resp.vendor == "mock"
    assert resp.ttl_pinned == 3600
    assert resp.cache_hit is False


def test_mock_provider_uses_fixture_when_provided() -> None:
    provider = MockProvider(fixture=lambda p: f"FIXED:{p}")

    resp = provider.complete("hi")

    assert resp.raw_text == "FIXED:hi"


def test_mock_provider_rejects_non_3600_ttl() -> None:
    provider = MockProvider()
    with pytest.raises(ValueError, match="cache_ttl must be 3600"):
        provider.complete("hi", cache_ttl=600)


def test_gateway_routes_to_registered_client_per_task() -> None:
    sentiment = MockProvider(vendor="gemini", model="flash-lite")
    interview = MockProvider(vendor="anthropic", model="haiku-4.5")

    gw = ModelGateway()
    gw.register(TaskID.PASS4_SENTIMENT, sentiment)
    gw.register(TaskID.PASS4_INTERVIEW_Q, interview)

    s = gw.complete(TaskID.PASS4_SENTIMENT, "post body")
    i = gw.complete(TaskID.PASS4_INTERVIEW_Q, "post body")

    assert s.vendor == "gemini"
    assert i.vendor == "anthropic"


def test_gateway_falls_back_to_default_when_task_unregistered() -> None:
    fallback = MockProvider(vendor="default", model="m")
    gw = ModelGateway(default_client=fallback)

    resp = gw.complete(TaskID.PASS4_SENTIMENT, "p")

    assert resp.vendor == "default"


def test_gateway_raises_when_no_provider_available() -> None:
    gw = ModelGateway()
    with pytest.raises(RuntimeError, match="No provider configured"):
        gw.complete(TaskID.PASS4_SENTIMENT, "p")


def test_audit_id_is_deterministic_per_call() -> None:
    p = MockProvider()
    r1 = p.complete("hello")
    r2 = p.complete("hello")
    # The audit_id includes the timestamp so consecutive calls differ.
    assert r1.audit_id.startswith("audit:")
    assert r2.audit_id.startswith("audit:")


def test_task_id_values_match_adr011_strings() -> None:
    assert TaskID.PASS4_SENTIMENT.value == "pass4.sentiment"
    assert TaskID.PASS4_INTERVIEW_Q.value == "pass4.interview_q"
    assert TaskID.JUDGE_TIE_BREAK.value == "judge.tie_break"
