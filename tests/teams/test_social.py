"""Tests for V1.5c Social trending-topic aggregator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.teams.social import TopicMention, compute_trending_topics


def _mention(
    topic: str, days_ago: int, sentiment: float = 0.0,
    source_id: str | None = None,
) -> TopicMention:
    return TopicMention(
        topic=topic,
        timestamp=datetime.now(UTC) - timedelta(days=days_ago),
        source_id=source_id or f"post:{topic}:{days_ago}",
        sentiment=sentiment,
    )


def test_empty_inputs_returns_empty() -> None:
    assert compute_trending_topics([]) == []


def test_trend_detected_when_window_volume_exceeds_baseline() -> None:
    mentions = [
        # Recent burst (within 30-day window)
        *(_mention("dat_anxiety", days_ago=d) for d in range(10)),
        # Older baseline (older than window, within baseline_days)
        *(_mention("dat_anxiety", days_ago=d) for d in range(45, 50)),
    ]
    trends = compute_trending_topics(mentions, min_trend_ratio=1.5)
    by_topic = {t.topic_id: t for t in trends}
    assert "topic:dat_anxiety" in by_topic
    assert by_topic["topic:dat_anxiety"].window_volume == 10


def test_no_trend_when_below_ratio() -> None:
    mentions = [
        *(_mention("steady_topic", days_ago=d) for d in range(0, 10, 2)),
        *(_mention("steady_topic", days_ago=d) for d in range(50, 80)),
    ]
    trends = compute_trending_topics(mentions, min_trend_ratio=10.0)
    assert trends == []


def test_daily_buckets_populated() -> None:
    mentions = [
        _mention("daily", days_ago=0, sentiment=0.5, source_id="d0"),
        _mention("daily", days_ago=0, sentiment=0.3, source_id="d0b"),
        _mention("daily", days_ago=1, sentiment=-0.2, source_id="d1"),
    ]
    trends = compute_trending_topics(mentions, min_trend_ratio=1.0)
    assert trends
    assert len(trends[0].daily_buckets) == 2


def test_seed_corpus_yields_five_trending_topics() -> None:
    """AC-5 sketch — synthetic burst across 5 topics yields ≥ 5 trends."""

    mentions = []
    for topic_idx in range(5):
        topic = f"topic_{topic_idx}"
        mentions.extend(_mention(topic, days_ago=d) for d in range(20))
    trends = compute_trending_topics(mentions, min_trend_ratio=1.0)
    assert len(trends) >= 5


def test_avg_sentiment_in_window() -> None:
    mentions = [
        _mention("t", days_ago=d, sentiment=0.5)
        for d in range(10)
    ]
    trends = compute_trending_topics(mentions, min_trend_ratio=1.0)
    assert abs(trends[0].avg_sentiment - 0.5) < 1e-6
