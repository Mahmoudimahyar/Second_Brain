"""Tests for V1.5c Marketing content-gap aggregator."""

from __future__ import annotations

from src.teams.marketing import MarketingMention, compute_content_gaps


def test_empty_returns_empty() -> None:
    assert compute_content_gaps([]) == []


def test_topic_below_min_volume_skipped() -> None:
    mentions = [
        MarketingMention("a", -0.8, "1"),
        MarketingMention("a", -0.7, "2"),  # only 2 < min_volume=3
    ]
    assert compute_content_gaps(mentions, min_volume=3) == []


def test_positive_sentiment_not_a_gap() -> None:
    mentions = [
        MarketingMention("a", 0.5, f"src:{i}") for i in range(5)
    ]
    assert compute_content_gaps(mentions, min_volume=3) == []


def test_negative_sentiment_high_volume_is_a_gap() -> None:
    mentions = [
        MarketingMention("frustrating_topic", -0.6, f"src:{i}")
        for i in range(5)
    ]
    gaps = compute_content_gaps(mentions, min_volume=3)
    assert len(gaps) == 1
    assert gaps[0].volume == 5
    assert gaps[0].avg_sentiment < 0


def test_gap_severity_orders_by_volume_and_negativity() -> None:
    mentions = [
        # Topic A: 5 mentions at -0.3
        *(MarketingMention("a", -0.3, f"a:{i}") for i in range(5)),
        # Topic B: 3 mentions at -0.9 (more negative but lower volume)
        *(MarketingMention("b", -0.9, f"b:{i}") for i in range(3)),
    ]
    gaps = compute_content_gaps(mentions, min_volume=3)
    assert len(gaps) == 2
    # severity = volume * (-avg_sentiment + 0.1)
    # A: 5 * (0.3 + 0.1) = 2.0
    # B: 3 * (0.9 + 0.1) = 3.0
    assert gaps[0].topic.lower().startswith("b")


def test_seed_corpus_yields_five_content_gaps() -> None:
    """AC-6 sketch — synthetic 5-topic negative-sentiment corpus."""

    mentions = []
    for idx in range(5):
        mentions.extend(
            MarketingMention(f"topic_{idx}", -0.5 - idx * 0.05, f"src:{idx}:{j}")
            for j in range(4)
        )
    gaps = compute_content_gaps(mentions, min_volume=3)
    assert len(gaps) >= 5


def test_references_deduplicated() -> None:
    mentions = [
        MarketingMention("t", -0.5, "src:1"),
        MarketingMention("t", -0.5, "src:1"),
        MarketingMention("t", -0.5, "src:2"),
    ]
    gap = compute_content_gaps(mentions, min_volume=3)[0]
    assert sorted(gap.references) == ["src:1", "src:2"]
