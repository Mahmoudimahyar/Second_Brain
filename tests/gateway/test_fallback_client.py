"""Tests for `src.gateway.api.FallbackClient` runtime circuit-breaker.

When a primary LLMClient raises mid-call, the FallbackClient routes the same
request to a secondary client. This closes GAP-046 fully for live runs
(previous fix only handled the env-time `ANTHROPIC_API_KEY` missing case).
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import BaseModel

from src.gateway import TaskID, default_gateway
from src.gateway.api import FallbackClient, GatewayResponse, MockProvider


def _response(vendor: str) -> GatewayResponse:
    return GatewayResponse(
        vendor=vendor, model=f"{vendor}-test",
        output=None, raw_text="ok",
        input_tokens=1, output_tokens=1, cached_input_tokens=0,
        cost_usd=0.0, latency_ms=0.0,
        cache_hit=False, audit_id="audit:test", ttl_pinned=3600,
    )


@dataclass
class _RaisingClient:
    vendor: str = "primary"
    model: str = "primary-test"
    raise_count: int = 1
    _calls: int = 0

    def complete(
        self,
        prompt: str,
        *,
        schema: type[BaseModel] | None = None,
        cache_key: str | None = None,
        cache_ttl: int = 3600,
    ) -> GatewayResponse:
        self._calls += 1
        if self._calls <= self.raise_count:
            raise RuntimeError(f"simulated failure {self._calls}")
        return _response(self.vendor)


def test_primary_success_does_not_invoke_fallback() -> None:
    primary = MockProvider(vendor="primary", model="p")
    fallback = MockProvider(vendor="fallback", model="f")
    client = FallbackClient(primary=primary, fallback=fallback)

    resp = client.complete("hello world")

    assert resp.vendor == "primary"


def test_primary_failure_falls_through_to_secondary() -> None:
    primary = _RaisingClient()
    fallback = MockProvider(vendor="fallback", model="f")
    client = FallbackClient(primary=primary, fallback=fallback)

    resp = client.complete("hello world")

    assert resp.vendor == "fallback"
    assert primary._calls == 1


def test_both_failing_raises_secondary_error() -> None:
    primary = _RaisingClient(vendor="p1")
    secondary = _RaisingClient(vendor="p2")
    client = FallbackClient(primary=primary, fallback=secondary)

    with pytest.raises(RuntimeError, match="simulated failure"):
        client.complete("hello")


def test_vendor_field_reports_active_provider() -> None:
    """FallbackClient.vendor reflects the *configured* primary; once
    a request lands on fallback, the response.vendor surfaces that."""

    primary = _RaisingClient(vendor="anthropic")
    fallback = MockProvider(vendor="openai", model="f")
    client = FallbackClient(primary=primary, fallback=fallback)

    assert client.vendor == "anthropic"  # static config
    resp = client.complete("hi")
    assert resp.vendor == "openai"       # actual provider used


def test_default_gateway_wires_fallback_when_both_keys_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "stub")
    monkeypatch.setenv("OPENAI_API_KEY", "stub")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    gw = default_gateway()
    # interview-Q now leads OpenAI (gpt-5-mini) with an Anthropic fallback (ADR-003
    # refresh 2026-05-30); conflict-candidate stays Anthropic-primary.
    interview = gw.task_to_client[TaskID.PASS4_INTERVIEW_Q]
    assert isinstance(interview, FallbackClient)
    assert interview.vendor == "openai"
    assert interview.fallback.vendor == "anthropic"

    conflict = gw.task_to_client[TaskID.PASS4_CONFLICT_CANDIDATE]
    assert isinstance(conflict, FallbackClient)
    assert conflict.vendor == "anthropic"
    assert conflict.fallback.vendor == "openai"


def test_default_gateway_no_fallback_when_only_anthropic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "stub")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    gw = default_gateway()
    client = gw.task_to_client[TaskID.PASS4_INTERVIEW_Q]
    assert not isinstance(client, FallbackClient)
    assert client.vendor == "anthropic"
