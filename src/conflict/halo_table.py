"""HALO per-edge-type half-life decay (ADR-007, GAP-050).

A 2014 tuition claim should weigh less in 2026 than a 2024 one, but a
`founding_year` never decays — so decay is **per-edge-type**, not global. V1
uses the hand-set half-life table below; V1.1 may learn it from data.

Wired into the retrieval ranker (`src/retrieval/ranking.py`) per ADR-021.
"""

from __future__ import annotations

import math
from datetime import datetime

# Half-lives in DAYS (ADR-007 V1 table). `inf` = never decays.
HALF_LIVES_DAYS: dict[str, float] = {
    "tuition": 365.0,
    "avg_DAT": 730.0,
    "avg_GPA": 730.0,
    "interview_format": 1095.0,
    "interview_question_reported": 1095.0,
    "program_requirement": 730.0,
    "founding_year": math.inf,
    "school_attribute": math.inf,
    "opinion_sentiment": 182.0,
    "applicant_anecdote": 730.0,
    "policy_advice": 365.0,
}

# Conservative default for unmapped types (ADR-007: "1 year (default)").
DEFAULT_HALF_LIFE_DAYS: float = 365.0


def half_life_days(edge_type: str | None) -> float:
    """Half-life for an edge/claim type, falling back to the 1-year default."""
    if not edge_type:
        return DEFAULT_HALF_LIFE_DAYS
    return HALF_LIVES_DAYS.get(edge_type, DEFAULT_HALF_LIFE_DAYS)


def decay(now: datetime, t_valid_from: datetime | None, edge_type: str | None) -> float:
    """Exponential decay ``2 ** (-(now - t_valid_from) / half_life)`` (ADR-007).

    Returns ``1.0`` (no decay) when the type never decays, when ``t_valid_from``
    is unknown, or when the fact is dated now/in the future.
    """
    hl = half_life_days(edge_type)
    if math.isinf(hl) or t_valid_from is None:
        return 1.0
    age_days = (now - t_valid_from).total_seconds() / 86_400.0
    if age_days <= 0:
        return 1.0
    return float(2.0 ** (-age_days / hl))
