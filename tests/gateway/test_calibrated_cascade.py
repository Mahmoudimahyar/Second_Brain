"""WP4.4 / ADR-023 — calibrated cascade (escalate on calibrated confidence).

Cheapest-tier-first; escalate only when the calibrated confidence is below the
tier threshold. On a confident sweep the strong tier is never called
(cost-regression: never costs more than always-strong).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel

from src.gateway.api import GatewayResponse
from src.gateway.calibration import IdentityCalibrator, IsotonicCalibrator
from src.gateway.routing import CalibratedCascade, CascadeTier


class _Conf(BaseModel):
    confidence: float = 1.0


@dataclass
class _CountingClient:
    vendor: str
    model: str
    conf: float
    calls: list[str] = field(default_factory=list)

    def complete(self, prompt: str, *, schema=None, cache_key=None, cache_ttl=3600):
        self.calls.append(prompt)
        return GatewayResponse(
            vendor=self.vendor, model=self.model, output=_Conf(confidence=self.conf),
            raw_text="", input_tokens=0, output_tokens=0, cached_input_tokens=0,
            cost_usd=0.0, latency_ms=0.0, cache_hit=False, audit_id="x", ttl_pinned=3600,
        )


def _cascade(cheap: _CountingClient, strong: _CountingClient, **kw):
    return CalibratedCascade(
        tiers=[CascadeTier(client=cheap, min_confidence=0.7),
               CascadeTier(client=strong, min_confidence=0.0)],
        **kw,
    )


def test_stops_when_cheap_tier_is_confident() -> None:
    cheap = _CountingClient("gemini", "flash-lite", conf=0.9)
    strong = _CountingClient("anthropic", "sonnet", conf=1.0)
    resp = _cascade(cheap, strong).complete("p")
    assert resp.vendor == "gemini"        # cheap answer accepted
    assert strong.calls == []             # strong never invoked


def test_escalates_when_cheap_tier_unconfident() -> None:
    cheap = _CountingClient("gemini", "flash-lite", conf=0.5)
    strong = _CountingClient("anthropic", "sonnet", conf=1.0)
    resp = _cascade(cheap, strong).complete("p")
    assert resp.vendor == "anthropic"     # escalated
    assert len(cheap.calls) == 1 and len(strong.calls) == 1


def test_cost_regression_no_escalation_on_confident_sweep() -> None:
    cheap = _CountingClient("gemini", "flash-lite", conf=0.95)
    strong = _CountingClient("anthropic", "sonnet", conf=1.0)
    casc = _cascade(cheap, strong)
    for i in range(10):
        casc.complete(f"item-{i}")
    assert len(cheap.calls) == 10
    assert strong.calls == []             # zero escalation → no spend increase


def test_single_tier_is_passthrough() -> None:
    only = _CountingClient("gemini", "flash-lite", conf=0.1)  # low conf, no tier to escalate to
    casc = CalibratedCascade(tiers=[CascadeTier(client=only, min_confidence=0.7)])
    assert casc.complete("p").vendor == "gemini"


def test_cascade_is_an_llm_client() -> None:
    cheap = _CountingClient("gemini", "flash-lite", conf=0.9)
    strong = _CountingClient("anthropic", "sonnet", conf=1.0)
    casc = _cascade(cheap, strong)
    assert casc.vendor == "gemini" and casc.model == "flash-lite"
    assert hasattr(casc, "complete")


def test_calibration_changes_escalation_decision() -> None:
    # Raw 0.9 would normally pass the 0.7 bar; a calibrator that maps high raw
    # confidence DOWN flips the decision to escalate.
    cheap = _CountingClient("gemini", "flash-lite", conf=0.9)
    strong = _CountingClient("anthropic", "sonnet", conf=1.0)
    cal = IsotonicCalibrator()
    cal.fit(raw=[0.1, 0.5, 0.9], correct=[False, False, False])  # 0.9 → ~0.0
    resp = _cascade(cheap, strong, calibrator=cal).complete("p")
    assert resp.vendor == "anthropic"     # calibrated-down → escalated


def test_identity_calibrator_clamps() -> None:
    c = IdentityCalibrator()
    assert c.calibrate(0.5) == 0.5
    assert c.calibrate(1.7) == 1.0
    assert c.calibrate(-0.2) == 0.0


def test_isotonic_identity_until_fit() -> None:
    c = IsotonicCalibrator()
    assert c.calibrate(0.42) == 0.42      # passthrough before fit
    c.fit(raw=[0.0, 1.0], correct=[True, True])
    assert 0.0 <= c.calibrate(0.42) <= 1.0
