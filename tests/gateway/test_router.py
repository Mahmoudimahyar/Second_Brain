"""WP4.4 / ADR-023 — optional learned first-hop router (RouteLLM-style).

Default off (no router) → start at the cheapest tier. A router may skip cheap
tiers for clearly-hard inputs (config-gated; default off until trained on traces).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel

from src.gateway.api import GatewayResponse
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


@dataclass(frozen=True)
class _FixedRouter:
    tier: int

    def first_hop(self, prompt: str, *, n_tiers: int) -> int:
        _ = prompt, n_tiers
        return self.tier


def _tiers() -> tuple[_CountingClient, _CountingClient]:
    return (
        _CountingClient("gemini", "flash-lite", conf=0.95),
        _CountingClient("anthropic", "sonnet", conf=1.0),
    )


def test_no_router_starts_at_cheapest_tier() -> None:
    cheap, strong = _tiers()
    casc = CalibratedCascade(tiers=[CascadeTier(cheap, 0.7), CascadeTier(strong, 0.0)])
    casc.complete("p")
    assert len(cheap.calls) == 1 and strong.calls == []  # started at tier 0


def test_router_skips_cheap_tier() -> None:
    cheap, strong = _tiers()
    casc = CalibratedCascade(
        tiers=[CascadeTier(cheap, 0.7), CascadeTier(strong, 0.0)],
        router=_FixedRouter(tier=1),  # route straight to the strong tier
    )
    resp = casc.complete("hard input")
    assert cheap.calls == [] and len(strong.calls) == 1
    assert resp.vendor == "anthropic"


def test_router_index_is_clamped() -> None:
    cheap, strong = _tiers()
    casc = CalibratedCascade(
        tiers=[CascadeTier(cheap, 0.7), CascadeTier(strong, 0.0)],
        router=_FixedRouter(tier=99),  # out of range → clamp to last tier
    )
    casc.complete("p")
    assert cheap.calls == [] and len(strong.calls) == 1
