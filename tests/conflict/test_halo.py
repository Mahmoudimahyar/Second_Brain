"""WP3.2 / ADR-007 — HALO per-edge-type half-life decay (GAP-050)."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from src.conflict.halo_table import (
    DEFAULT_HALF_LIFE_DAYS,
    HALF_LIVES_DAYS,
    decay,
    half_life_days,
)


def test_half_life_lookup_and_default() -> None:
    assert half_life_days("tuition") == HALF_LIVES_DAYS["tuition"] == 365.0
    assert half_life_days("opinion_sentiment") == 182.0
    assert math.isinf(half_life_days("founding_year"))
    assert half_life_days("unmapped_type") == DEFAULT_HALF_LIFE_DAYS
    assert half_life_days(None) == DEFAULT_HALF_LIFE_DAYS


def test_decay_halves_at_one_half_life() -> None:
    now = datetime(2025, 1, 1, tzinfo=UTC)
    one_hl_ago = now - timedelta(days=365)
    assert abs(decay(now, one_hl_ago, "tuition") - 0.5) < 0.02


def test_decay_never_for_infinite_half_life() -> None:
    now = datetime(2025, 1, 1, tzinfo=UTC)
    assert decay(now, datetime(1900, 1, 1, tzinfo=UTC), "founding_year") == 1.0


def test_decay_no_penalty_for_unknown_or_future() -> None:
    now = datetime(2025, 1, 1, tzinfo=UTC)
    assert decay(now, None, "tuition") == 1.0
    assert decay(now, datetime(2026, 1, 1, tzinfo=UTC), "tuition") == 1.0


def test_decay_monotonic_decreasing_with_age() -> None:
    now = datetime(2025, 1, 1, tzinfo=UTC)
    recent = decay(now, datetime(2024, 6, 1, tzinfo=UTC), "tuition")
    old = decay(now, datetime(2020, 1, 1, tzinfo=UTC), "tuition")
    assert recent > old


@given(age_days=st.floats(min_value=0.1, max_value=4000.0))
def test_decay_in_unit_interval(age_days: float) -> None:
    now = datetime(2025, 1, 1, tzinfo=UTC)
    d = decay(now, now - timedelta(days=age_days), "tuition")
    assert 0.0 < d <= 1.0
