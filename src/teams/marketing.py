"""V1.5c — Marketing/SEO dashboard aggregation (FR-1.5c-4 + AC-6).

Detects content gaps: topics with high volume but no positive consensus
(avg_sentiment < 0). Each gap represents a marketing opportunity.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field


@dataclass
class MarketingMention:
    """One mention of a topic with sentiment + source."""

    topic: str
    sentiment: float       # -1 → 1
    source_id: str
    excerpt: str = ""


class ContentGap(BaseModel):
    """One content gap surfaced for the marketing dashboard."""

    model_config = ConfigDict(extra="forbid")

    gap_id: str
    topic: str
    volume: int
    avg_sentiment: float
    gap_severity: float            # higher = louder gap (volume * |sentiment_negativity|)
    references: list[str] = Field(default_factory=list)
    sample_excerpts: list[str] = Field(default_factory=list)


def compute_content_gaps(
    mentions: Iterable[MarketingMention],
    *,
    min_volume: int = 3,
    max_sentiment_for_gap: float = 0.0,
) -> list[ContentGap]:
    """A topic is a gap iff (volume ≥ min_volume) AND
    (avg_sentiment < max_sentiment_for_gap). Ranked by gap_severity desc.
    """

    by_topic: dict[str, list[MarketingMention]] = defaultdict(list)
    for m in mentions:
        by_topic[m.topic].append(m)

    out: list[ContentGap] = []
    for topic, bucket in by_topic.items():
        if len(bucket) < min_volume:
            continue
        avg_sentiment = sum(m.sentiment for m in bucket) / len(bucket)
        if avg_sentiment >= max_sentiment_for_gap:
            continue
        severity = len(bucket) * max(0.0, -avg_sentiment + 0.1)
        excerpts = [m.excerpt[:240] for m in bucket[:3] if m.excerpt]
        out.append(ContentGap(
            gap_id=f"gap:{topic}",
            topic=_humanize(topic),
            volume=len(bucket),
            avg_sentiment=avg_sentiment,
            gap_severity=severity,
            references=sorted({m.source_id for m in bucket}),
            sample_excerpts=excerpts,
        ))
    out.sort(key=lambda g: g.gap_severity, reverse=True)
    return out


def _humanize(topic: str) -> str:
    return " ".join(w.capitalize() for w in topic.replace("_", " ").split())


__all__ = ["ContentGap", "MarketingMention", "compute_content_gaps"]
