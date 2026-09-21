"""Calibrated cascade routing + optional learned first-hop router (ADR-023).

Runs tiers cheapest-first and escalates when the *calibrated* confidence of a
tier's answer is below that tier's threshold. An optional `FirstHopRouter`
(RouteLLM-style) may skip cheap tiers for clearly-hard inputs — default off
until trained on Langfuse traces. `CalibratedCascade` is itself an `LLMClient`,
so it drops into the gateway's per-task routing (non-negotiable #12).

With the default `IdentityCalibrator` + no router, a single-tier cascade is a
no-op pass-through and a multi-tier cascade only escalates the genuinely
low-confidence tail — so it never costs more than always using the top tier
(cost-regression, ADR-023).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel

from src.gateway.api import GatewayResponse, LLMClient
from src.gateway.calibration import Calibrator, IdentityCalibrator

ConfidenceFn = Callable[[GatewayResponse], float]


def schema_confidence(resp: GatewayResponse) -> float:
    """Raw confidence from the parsed schema's ``confidence`` field; ``1.0`` when
    absent (no signal → treat as confident → do not escalate)."""
    val = getattr(resp.output, "confidence", None)
    if isinstance(val, (int, float)):
        return float(val)
    return 1.0


class FirstHopRouter(Protocol):
    """Predict the cheapest tier index that can likely handle the input."""

    def first_hop(self, prompt: str, *, n_tiers: int) -> int: ...


@dataclass(frozen=True)
class CascadeTier:
    client: LLMClient
    min_confidence: float  # accept this tier when calibrated confidence >= this


@dataclass
class CalibratedCascade:
    tiers: list[CascadeTier]
    confidence_of: ConfidenceFn = schema_confidence
    calibrator: Calibrator = field(default_factory=IdentityCalibrator)
    router: FirstHopRouter | None = None

    vendor: str = field(init=False)
    model: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.tiers:
            raise ValueError("CalibratedCascade needs at least one tier")
        self.vendor = self.tiers[0].client.vendor
        self.model = self.tiers[0].client.model

    def complete(
        self,
        prompt: str,
        *,
        schema: type[BaseModel] | None = None,
        cache_key: str | None = None,
        cache_ttl: int = 3600,
    ) -> GatewayResponse:
        start = 0
        if self.router is not None:
            hop = self.router.first_hop(prompt, n_tiers=len(self.tiers))
            start = max(0, min(hop, len(self.tiers) - 1))

        last: GatewayResponse | None = None
        for tier in self.tiers[start:]:
            resp = tier.client.complete(
                prompt, schema=schema, cache_key=cache_key, cache_ttl=cache_ttl,
            )
            last = resp
            if self.calibrator.calibrate(self.confidence_of(resp)) >= tier.min_confidence:
                return resp  # confident enough — stop escalating
        assert last is not None  # tiers is non-empty
        return last  # exhausted tiers → strongest tier's answer
