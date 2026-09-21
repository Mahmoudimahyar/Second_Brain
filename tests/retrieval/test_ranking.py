"""WP3.2 / ADR-021 — tier-as-prior ranking + RA-RAG consistency (GAP-048).

Includes the minority-correct regression fixture: a fresh, corroborated L5
claim MUST be able to outrank a stale L1 record (the failure mode the old
lexicographic "tier-first sort" baked in).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src.retrieval.consistency import SourceClaim, consistency, reliability
from src.retrieval.ranking import (
    rank_query_results,
    ranking_score,
)

# ---- ranking_score --------------------------------------------------------


def test_ranking_score_l1_preferred_is_one() -> None:
    assert ranking_score(
        source_tier="L1", rank="preferred", decay_factor=1.0,
        credibility=1.0, consistency_factor=1.0,
    ) == 1.0


def test_ranking_score_l5_prior_below_l1() -> None:
    s5 = ranking_score(source_tier="L5", rank="preferred", decay_factor=1.0,
                       credibility=1.0, consistency_factor=1.0)
    assert abs(s5 - 0.4) < 1e-9  # L5 prior


def test_deprecated_rank_zeroes_the_score() -> None:
    assert ranking_score(source_tier="L1", rank="deprecated", decay_factor=1.0,
                         credibility=1.0, consistency_factor=1.0) == 0.0


# ---- consistency ----------------------------------------------------------


def test_reliability_is_tier_times_credibility() -> None:
    assert abs(reliability("L1", 1.0) - 1.0) < 1e-9
    assert abs(reliability("L5", 0.5) - 0.2) < 1e-9


def test_lone_claim_is_neutral() -> None:
    c = SourceClaim(value="x", source_tier="L1")
    assert consistency(c, [c]) == 1.0


def test_corroborated_minority_scores_above_isolated_official() -> None:
    l1 = SourceClaim(value="old", source_tier="L1")
    l5 = [SourceClaim(value="new", source_tier="L5") for _ in range(3)]
    peers = [l1, *l5]
    assert consistency(l5[0], peers) > consistency(l1, peers)


# ---- minority-correct regression fixture ----------------------------------


@dataclass
class _Result:
    node_id: str
    node_type: str
    source_tier: str
    rank: str
    t_valid_from: datetime | None
    properties: dict[str, Any]


def _claim(node_id: str, tier: str, t: datetime, value: str) -> _Result:
    return _Result(
        node_id=node_id, node_type="Claim", source_tier=tier, rank="normal",
        t_valid_from=t,
        properties={
            "subject_id": "school:nyu", "predicate": "casper_required",
            "object_value": value,
        },
    )


def test_minority_correct_fresh_l5_outranks_stale_l1() -> None:
    now = datetime(2026, 5, 29, tzinfo=UTC)
    stale = datetime(2019, 1, 1, tzinfo=UTC)   # ~7y old -> low HALO decay
    fresh = datetime(2026, 3, 1, tzinfo=UTC)   # recent -> decay ~1

    l1 = _claim("l1", "L1", stale, "no")
    l5a = _claim("l5a", "L5", fresh, "yes")
    l5b = _claim("l5b", "L5", fresh, "yes")
    l5c = _claim("l5c", "L5", fresh, "yes")

    ranked = rank_query_results([l1, l5a, l5b, l5c], now=now)

    # The fresh, corroborated L5 cluster outranks the stale L1 record...
    assert ranked[0].source_tier == "L5"
    # ...and the stale L1 record sinks to the bottom (not buried-by-tier at top).
    assert ranked[-1].node_id == "l1"


def test_all_else_equal_l1_still_dominates() -> None:
    # Tier remains a strong prior: same recency/consistency -> L1 wins.
    now = datetime(2026, 5, 29, tzinfo=UTC)
    fresh = datetime(2026, 3, 1, tzinfo=UTC)
    l1 = _claim("l1", "L1", fresh, "same")
    l5 = _claim("l5", "L5", fresh, "same")
    ranked = rank_query_results([l5, l1], now=now)
    assert ranked[0].node_id == "l1"
