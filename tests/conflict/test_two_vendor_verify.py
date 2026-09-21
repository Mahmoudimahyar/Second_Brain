"""W1-2 — Two-vendor parallel verify in signal C (ADR-016 v2 §3 step 4).

Failing-first tests for the parallel Haiku 4.5 + Gemini Flash verification.
Both vendors run in parallel via a thread pool; both must return the same
verdict for signal C to count, otherwise signal C = ``disagreement``.

Per-vendor 6s timeout (ADR-016 v2 §9). If exactly one vendor returns,
degraded mode emits the surviving vendor's verdict with ``low_confidence``.
If both fail, signal C = ``unknown`` with confidence 0.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from src.conflict.baml.templates import (
    TwoVendorVerifyOutcome,
    VendorVerifyResult,
    VerifyResult,
    verify_claim_two_vendor_via_gateway,
)
from src.gateway.api import GatewayResponse, ModelGateway, TaskID


def _ok_response(verdict: str, conf: float, excerpt: str) -> GatewayResponse:
    return GatewayResponse(
        vendor="mock",
        model="mock-v1",
        output=None,
        raw_text=(
            '{"verdict": "' + verdict + '", '
            '"evidence_excerpt": "' + excerpt + '", '
            '"confidence": ' + str(conf) + '}'
        ),
        input_tokens=10,
        output_tokens=10,
        cached_input_tokens=0,
        cost_usd=0.0,
        latency_ms=1.0,
        cache_hit=False,
        audit_id="audit:test",
    )


def _slow_response(seconds: float, verdict: str = "supports") -> GatewayResponse:
    time.sleep(seconds)
    return _ok_response(verdict, 0.9, "slow but eventually done")


def test_both_vendors_agree_returns_agreed_verdict() -> None:
    gw = MagicMock(spec=ModelGateway)
    gw.complete.side_effect = lambda task, prompt: (
        _ok_response("supports", 0.9, "evidence haiku")
        if task == TaskID.WEB_VERIFY_CLAIM_HAIKU
        else _ok_response("supports", 0.95, "evidence gemini")
    )

    outcome = verify_claim_two_vendor_via_gateway(
        "claim", "evidence", gateway=gw,
    )

    assert isinstance(outcome, TwoVendorVerifyOutcome)
    assert outcome.final.verdict == "supports"
    assert outcome.haiku.verdict == "supports"
    assert outcome.gemini.verdict == "supports"
    assert not outcome.degraded
    # Confidence = mean of both vendors
    assert 0.9 <= outcome.final.confidence <= 0.95
    assert outcome.haiku.error is None
    assert outcome.gemini.error is None


def test_vendors_disagree_returns_disagreement_verdict() -> None:
    gw = MagicMock(spec=ModelGateway)
    gw.complete.side_effect = lambda task, prompt: (
        _ok_response("supports", 0.9, "haiku says yes")
        if task == TaskID.WEB_VERIFY_CLAIM_HAIKU
        else _ok_response("refutes", 0.85, "gemini says no")
    )

    outcome = verify_claim_two_vendor_via_gateway(
        "claim", "evidence", gateway=gw,
    )

    assert outcome.final.verdict == "disagreement"
    assert outcome.final.confidence == 0.0
    assert outcome.haiku.verdict == "supports"
    assert outcome.gemini.verdict == "refutes"
    assert not outcome.degraded


def test_one_vendor_timeout_degraded_mode() -> None:
    """If exactly one vendor times out, degraded mode emits the surviving
    vendor's verdict with confidence halved + ``degraded=True``."""

    gw = MagicMock(spec=ModelGateway)

    def slow_or_fast(task: TaskID, prompt: str) -> GatewayResponse:
        if task == TaskID.WEB_VERIFY_CLAIM_HAIKU:
            return _ok_response("supports", 0.9, "haiku ok")
        # Gemini takes 5s; with per_vendor_timeout_s=0.2 it should time out
        return _slow_response(5.0, "supports")

    gw.complete.side_effect = slow_or_fast

    outcome = verify_claim_two_vendor_via_gateway(
        "claim", "evidence", gateway=gw, per_vendor_timeout_s=0.2,
    )

    assert outcome.degraded
    assert outcome.haiku.verdict == "supports"
    assert outcome.haiku.error is None
    assert outcome.gemini.error is not None  # timeout recorded
    # Degraded → final verdict matches the surviving vendor; confidence ≤ 0.5
    assert outcome.final.verdict == "supports"
    assert outcome.final.confidence <= 0.5


def test_both_vendors_fail_returns_unknown() -> None:
    gw = MagicMock(spec=ModelGateway)

    def always_5xx(task: TaskID, prompt: str) -> GatewayResponse:
        raise RuntimeError(f"5xx for {task.value}")

    gw.complete.side_effect = always_5xx

    outcome = verify_claim_two_vendor_via_gateway(
        "claim", "evidence", gateway=gw, per_vendor_timeout_s=2.0,
    )

    assert outcome.final.verdict == "unknown"
    assert outcome.final.confidence == 0.0
    assert outcome.haiku.error is not None
    assert outcome.gemini.error is not None
    # degraded=False because no vendor returned; this is the "both failed" path
    assert not outcome.degraded


def test_one_vendor_5xx_degraded_mode() -> None:
    """One vendor raises (5xx); the other succeeds → degraded mode."""

    gw = MagicMock(spec=ModelGateway)

    def haiku_dies_gemini_ok(task: TaskID, prompt: str) -> GatewayResponse:
        if task == TaskID.WEB_VERIFY_CLAIM_HAIKU:
            raise RuntimeError("anthropic 5xx")
        return _ok_response("refutes", 0.88, "gemini ok")

    gw.complete.side_effect = haiku_dies_gemini_ok

    outcome = verify_claim_two_vendor_via_gateway(
        "claim", "evidence", gateway=gw, per_vendor_timeout_s=2.0,
    )

    assert outcome.degraded
    assert outcome.haiku.error is not None
    assert outcome.gemini.error is None
    assert outcome.final.verdict == "refutes"  # surviving Gemini's verdict
    assert outcome.final.confidence <= 0.5     # halved confidence


def test_runs_vendors_in_parallel_not_serial() -> None:
    """Both vendors should start within ~50ms of each other; total wall
    time ≈ max(haiku_time, gemini_time), not sum."""

    gw = MagicMock(spec=ModelGateway)

    def both_take_500ms(task: TaskID, prompt: str) -> GatewayResponse:
        time.sleep(0.5)
        return _ok_response("supports", 0.9, "ok")

    gw.complete.side_effect = both_take_500ms

    start = time.perf_counter()
    outcome = verify_claim_two_vendor_via_gateway(
        "claim", "evidence", gateway=gw, per_vendor_timeout_s=5.0,
    )
    elapsed = time.perf_counter() - start

    assert outcome.final.verdict == "supports"
    # Parallel: should be ~500ms, NOT ~1000ms. Allow generous margin.
    assert elapsed < 0.8, f"expected parallel ~0.5s, got {elapsed:.2f}s"


# ---------------------------------------------------------------------
# WebVerificationAgent integration — signal_c carries vendor breakdown
# ---------------------------------------------------------------------


def test_web_verification_agent_default_uses_two_vendor_path() -> None:
    """Default agent (no verify override) routes signal C through
    verify_claim_two_vendor_via_gateway."""

    from src.conflict.providers.tavily import TavilyProvider  # noqa: PLC0415
    from src.conflict.web_verify import WebVerificationAgent  # noqa: PLC0415

    agent = WebVerificationAgent(
        provider=TavilyProvider(api_key="placeholder"),
    )

    # The agent should expose a verify_two_vendor callable; the legacy
    # single-vendor `verify` attribute may be None (default) or set.
    # Default: verify=None, verify_two_vendor != None.
    assert agent.verify is None
    assert agent.verify_two_vendor is not None


def test_signal_c_includes_per_vendor_breakdown_in_run() -> None:
    """When the two-vendor path is used, the WebVerificationRun.signal_c
    dict must include the per-vendor breakdown so the audit log captures
    both Haiku and Gemini outputs."""

    from dataclasses import dataclass, field  # noqa: PLC0415

    from src.conflict.providers.base import ExtractedPage, SearchAnswer  # noqa: PLC0415
    from src.conflict.web_verify import (  # noqa: PLC0415
        WebVerificationAgent,
    )

    @dataclass
    class _StubProvider:
        name: str = "tavily"
        qna_a: SearchAnswer = field(default_factory=lambda: SearchAnswer(
            answer="NYU tuition is $87000",
            urls=["https://nyu.edu"],
        ))
        search_a: SearchAnswer = field(default_factory=lambda: SearchAnswer(
            answer="NYU dental tuition $87000 yearly",
            urls=["https://dental.nyu.edu"],
        ))

        def qna_search(self, q: str, *, max_results: int = 5) -> SearchAnswer:
            return self.qna_a

        def search(self, q: str, *, max_results: int = 5,
                   search_depth: str = "advanced") -> SearchAnswer:
            return self.search_a

        def extract(self, urls: list[str], *,
                    extract_depth: str = "advanced") -> list[ExtractedPage]:
            return [
                ExtractedPage(
                    url=u, text="NYU dental tuition for 2024-25 was $87,062.",
                    success=True,
                )
                for u in urls
            ]

    def fake_two_vendor(claim: str, evidence: str) -> TwoVendorVerifyOutcome:
        haiku = VendorVerifyResult(
            vendor="haiku",
            verdict="supports",
            evidence_excerpt="tuition $87000",
            confidence=0.92,
            latency_ms=120.0,
        )
        gemini = VendorVerifyResult(
            vendor="gemini",
            verdict="supports",
            evidence_excerpt="tuition $87000 yearly",
            confidence=0.94,
            latency_ms=180.0,
        )
        return TwoVendorVerifyOutcome(
            final=VerifyResult(
                verdict="supports",
                evidence_excerpt="tuition $87000",
                confidence=0.93,
            ),
            haiku=haiku,
            gemini=gemini,
            degraded=False,
        )

    agent = WebVerificationAgent(
        provider=_StubProvider(),  # type: ignore[arg-type]
        verify_two_vendor=fake_two_vendor,
    )

    # Need to bypass make_question/paraphrase gateway calls — inject stubs.
    from src.conflict.baml.templates import (  # noqa: PLC0415
        ClaimQuestionMaker,
        QuestionParaphraser,
    )
    agent.make_question = ClaimQuestionMaker(
        invoke=lambda c: "Is NYU tuition $87000?",
    )
    agent.paraphrase = QuestionParaphraser(
        invoke=lambda q: "Does NYU charge $87000?",
    )

    result = agent.verify_claim("NYU dental tuition is $87000")
    sig_c = result.run.signal_c

    assert sig_c["verdict"] == "supports"
    assert "vendor_breakdown" in sig_c, (
        "signal_c must include per-vendor breakdown when two-vendor path is used"
    )
    breakdown = sig_c["vendor_breakdown"]
    assert breakdown["haiku"]["verdict"] == "supports"
    assert breakdown["haiku"]["confidence"] == 0.92
    assert breakdown["gemini"]["verdict"] == "supports"
    assert breakdown["gemini"]["confidence"] == 0.94
    assert breakdown["degraded"] is False


_ = pytest  # silence unused-import warning
