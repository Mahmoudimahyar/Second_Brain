"""Tests for V1.5c PM aggregator + V1.5d daily_buckets / tier_mix / top_clusters."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.teams.pm import (
    PainPointInput,
    compute_pain_points,
    compute_top_clusters,
)


def test_empty_inputs_returns_empty() -> None:
    assert compute_pain_points([]) == []


def test_aggregates_by_label_and_segment() -> None:
    inputs = [
        PainPointInput("tuition", "applicants", -0.8, "post:1", "tuition is brutal"),
        PainPointInput("tuition", "applicants", -0.7, "post:2", "tuition is too high"),
        PainPointInput("interview", "applicants", -0.3, "post:3", "interview nerves"),
    ]
    pps = compute_pain_points(inputs)
    by_id = {p.pain_point_id: p for p in pps}
    assert "pp:tuition:applicants" in by_id
    assert by_id["pp:tuition:applicants"].volume == 2
    assert abs(by_id["pp:tuition:applicants"].avg_sentiment + 0.75) < 1e-6


def test_min_volume_filters_out_singletons() -> None:
    inputs = [
        PainPointInput("a", "x", -1.0, "1"),
        PainPointInput("b", "x", -1.0, "2"),
        PainPointInput("b", "x", -0.5, "3"),
    ]
    pps = compute_pain_points(inputs, min_volume=2)
    assert {p.pain_point_id for p in pps} == {"pp:b:x"}


def test_ranks_by_volume_then_sentiment_magnitude() -> None:
    inputs = [
        PainPointInput("low_volume", "x", -0.9, "1"),
        PainPointInput("high_volume_a", "x", -0.2, "2"),
        PainPointInput("high_volume_a", "x", -0.3, "3"),
        PainPointInput("high_volume_a", "x", -0.1, "4"),
    ]
    pps = compute_pain_points(inputs)
    assert pps[0].pain_point_id == "pp:high_volume_a:x"


def test_references_deduplicated() -> None:
    inputs = [
        PainPointInput("a", "x", -1, "post:1"),
        PainPointInput("a", "x", -1, "post:1"),
        PainPointInput("a", "x", -1, "post:2"),
    ]
    pp = compute_pain_points(inputs)[0]
    assert sorted(pp.references) == ["post:1", "post:2"]


def test_evidence_excerpt_truncated() -> None:
    long_excerpt = "a" * 1000
    pp = compute_pain_points([
        PainPointInput("a", "x", -1, "1", long_excerpt),
        PainPointInput("a", "x", -1, "2", long_excerpt),
    ])[0]
    assert all(len(e.excerpt) <= 280 for e in pp.evidence)


def test_seed_corpus_yields_ten_pain_points() -> None:
    """AC-4 sketch — synthetic 10-label corpus yields ≥ 10 pain points."""

    inputs = []
    for label_idx in range(10):
        for _ in range(2):
            inputs.append(
                PainPointInput(
                    label=f"label_{label_idx}",
                    audience_segment="applicants",
                    sentiment=-0.5 - label_idx * 0.05,
                    source_id=f"post:{label_idx}:{_}",
                ),
            )
    pps = compute_pain_points(inputs, min_volume=2)
    assert len(pps) >= 10


# ----------------------------------------------------------------------
# V1.5d: daily_buckets + tier_mix + top_clusters
# ----------------------------------------------------------------------


def test_daily_buckets_empty_when_no_timestamps() -> None:
    inputs = [
        PainPointInput("a", "x", -0.5, "post:1"),
        PainPointInput("a", "x", -0.6, "post:2"),
    ]
    pp = compute_pain_points(inputs)[0]
    assert pp.daily_buckets == []


def test_daily_buckets_populated_when_timestamps_present() -> None:
    now = datetime.now(UTC)
    inputs = [
        PainPointInput("a", "x", -0.5, "post:1", timestamp=now - timedelta(days=1)),
        PainPointInput("a", "x", -0.7, "post:2", timestamp=now - timedelta(days=1)),
        PainPointInput("a", "x", -0.3, "post:3", timestamp=now - timedelta(days=3)),
    ]
    pp = compute_pain_points(inputs)[0]
    assert len(pp.daily_buckets) == 2
    # Sorted ascending by date.
    assert pp.daily_buckets[0].date < pp.daily_buckets[1].date
    # Day-1 bucket has volume 2 + avg of two sentiments.
    assert pp.daily_buckets[-1].volume == 2
    assert abs(pp.daily_buckets[-1].avg_sentiment + 0.6) < 1e-6


def test_daily_buckets_excludes_items_outside_window() -> None:
    now = datetime.now(UTC)
    inputs = [
        PainPointInput("a", "x", -0.5, "post:1", timestamp=now - timedelta(days=1)),
        PainPointInput("a", "x", -0.5, "post:2", timestamp=now - timedelta(days=60)),
    ]
    pp = compute_pain_points(inputs, trend_window_days=30)[0]
    # Old item excluded from buckets (but still in volume + references).
    assert len(pp.daily_buckets) == 1
    assert pp.volume == 2


def test_tier_mix_empty_when_no_tier() -> None:
    inputs = [
        PainPointInput("a", "x", -0.5, "post:1"),
        PainPointInput("a", "x", -0.6, "post:2"),
    ]
    pp = compute_pain_points(inputs)[0]
    assert pp.tier_mix == {}


def test_tier_mix_computes_per_tier_fraction() -> None:
    inputs = [
        PainPointInput("a", "x", -0.5, "post:1", source_tier="L5"),
        PainPointInput("a", "x", -0.5, "post:2", source_tier="L5"),
        PainPointInput("a", "x", -0.5, "post:3", source_tier="L1"),
    ]
    pp = compute_pain_points(inputs)[0]
    assert pp.tier_mix == {"L5": 2 / 3, "L1": 1 / 3}


def test_tier_mix_excludes_unknown_tier_inputs() -> None:
    inputs = [
        PainPointInput("a", "x", -0.5, "post:1", source_tier="L5"),
        PainPointInput("a", "x", -0.5, "post:2"),  # no tier
    ]
    pp = compute_pain_points(inputs)[0]
    assert pp.tier_mix == {"L5": 1.0}


def test_top_clusters_empty_when_no_cluster_ids() -> None:
    inputs = [
        PainPointInput("a", "x", -0.5, "post:1"),
        PainPointInput("a", "x", -0.5, "post:2"),
    ]
    assert compute_top_clusters(inputs) == []


def test_top_clusters_groups_and_sorts_by_count_desc() -> None:
    inputs = [
        PainPointInput("a", "x", -0.5, "p1", cluster_id="c:a", cluster_label="A"),
        PainPointInput("a", "x", -0.5, "p2", cluster_id="c:a", cluster_label="A"),
        PainPointInput("a", "x", -0.5, "p3", cluster_id="c:b", cluster_label="B"),
        PainPointInput("a", "x", -0.5, "p4"),  # no cluster — excluded
    ]
    rows = compute_top_clusters(inputs)
    assert [(r.cluster_id, r.label, r.count) for r in rows] == [
        ("c:a", "A", 2),
        ("c:b", "B", 1),
    ]
