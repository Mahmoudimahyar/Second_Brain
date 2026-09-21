"""Confidence calibration for the cascade (ADR-023).

Raw self-reported confidence / logprobs are overconfident + poorly calibrated
(FrugalGPT; UCCI arXiv 2605.18796; "Overconfidence in LLM-as-a-Judge"). Isotonic-
scale the signal so an escalation threshold means a real probability of
correctness. Identity (passthrough) until a labeled set (Langfuse traces) exists
— so wiring the cascade with the default calibrator changes nothing on its own.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol


class Calibrator(Protocol):
    def calibrate(self, raw: float) -> float: ...


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


@dataclass(frozen=True)
class IdentityCalibrator:
    """Passthrough (clamped to [0,1]) — the safe default pre-training."""

    def calibrate(self, raw: float) -> float:
        return _clamp(raw)


@dataclass
class IsotonicCalibrator:
    """Isotonic regression of raw confidence → P(correct). Identity until `fit`."""

    _model: Any = field(default=None, init=False, repr=False)

    def fit(self, raw: Sequence[float], correct: Sequence[bool]) -> None:
        from sklearn.isotonic import IsotonicRegression  # noqa: PLC0415

        model = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        model.fit(list(raw), [1.0 if c else 0.0 for c in correct])
        self._model = model

    def calibrate(self, raw: float) -> float:
        if self._model is None:
            return _clamp(raw)
        return _clamp(float(self._model.predict([raw])[0]))
