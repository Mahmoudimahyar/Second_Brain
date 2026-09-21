"""V1.5c — Social-media dashboard aggregation (FR-1.5c-4 + AC-5).

Computes trending topics over time windows. A topic "trends" if its
within-window volume is at least 2x the rolling-baseline volume.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field


@dataclass
class TopicMention:
    """One mention of a topic at a point in time."""

    topic: str
    timestamp: datetime
    source_id: str
    sentiment: float = 0.0
    excerpt: str = ""


class TrendBucket(BaseModel):
    """Per-day volume + sentiment for a trend chart."""

    model_config = ConfigDict(extra="forbid")

    date: str          # YYYY-MM-DD
    volume: int
    avg_sentiment: float


class TrendingTopic(BaseModel):
    """One trending topic surfaced by the aggregator."""

    model_config = ConfigDict(extra="forbid")

    topic_id: str
    name: str
    window_volume: int
    baseline_volume: int
    trend_ratio: float
    avg_sentiment: float
    references: list[str] = Field(default_factory=list)
    daily_buckets: list[TrendBucket] = Field(default_factory=list)


def compute_trending_topics(
    mentions: Iterable[TopicMention],
    *,
    window_days: int = 30,
    baseline_days: int = 180,
    min_trend_ratio: float = 2.0,
    as_of: datetime | None = None,
) -> list[TrendingTopic]:
    """Find topics whose within-`window_days` volume is >= `min_trend_ratio`
    of their rolling-baseline volume. Returns sorted by trend_ratio desc.
    """

    materialized = list(mentions)
    if not materialized:
        return []

    end = as_of or max(m.timestamp for m in materialized)
    window_start = end - timedelta(days=window_days)
    baseline_start = end - timedelta(days=baseline_days)

    window_counts: Counter[str] = Counter()
    baseline_counts: Counter[str] = Counter()
    window_sentiment: dict[str, list[float]] = {}
    window_refs: dict[str, set[str]] = {}
    window_per_day: dict[str, dict[str, list[float]]] = {}

    for m in materialized:
        if m.timestamp < baseline_start:
            continue
        if baseline_start <= m.timestamp < window_start:
            baseline_counts[m.topic] += 1
            continue
        # Within current window.
        window_counts[m.topic] += 1
        window_sentiment.setdefault(m.topic, []).append(m.sentiment)
        window_refs.setdefault(m.topic, set()).add(m.source_id)
        day = m.timestamp.date().isoformat()
        window_per_day.setdefault(m.topic, {}).setdefault(day, []).append(
            m.sentiment,
        )

    out: list[TrendingTopic] = []
    for topic, win_v in window_counts.items():
        # Baseline normalized to comparable window length.
        base_v_raw = baseline_counts.get(topic, 0)
        # Per-day rates so window vs baseline is comparable.
        win_rate = win_v / max(window_days, 1)
        base_rate = base_v_raw / max(baseline_days - window_days, 1)
        # Avoid div-by-zero — treat base_rate < 0.05 as 0.05.
        ratio = win_rate / max(base_rate, 0.05)
        if ratio < min_trend_ratio:
            continue
        sentiments = window_sentiment.get(topic, [0.0])
        avg_sent = sum(sentiments) / len(sentiments)
        buckets = [
            TrendBucket(
                date=day,
                volume=len(sents),
                avg_sentiment=sum(sents) / len(sents),
            )
            for day, sents in sorted(window_per_day.get(topic, {}).items())
        ]
        out.append(TrendingTopic(
            topic_id=f"topic:{topic}",
            name=_humanize_topic(topic),
            window_volume=win_v,
            baseline_volume=base_v_raw,
            trend_ratio=ratio,
            avg_sentiment=avg_sent,
            references=sorted(window_refs.get(topic, set())),
            daily_buckets=buckets,
        ))
    out.sort(key=lambda t: t.trend_ratio, reverse=True)
    return out


def _humanize_topic(topic: str) -> str:
    return " ".join(w.capitalize() for w in topic.replace("_", " ").split())


__all__ = ["TopicMention", "TrendBucket", "TrendingTopic", "compute_trending_topics"]
