"""V1.5c — PM dashboard aggregation (FR-1.5c-4 + AC-4).

Aggregates Pass-4 conflict-candidate + interview-Q + cluster sentiment into
ranked pain points per audience segment.

V1.5d addendum (2026-05-27): each PainPoint now carries

- ``daily_buckets`` — last-N-day rolling count + avg-sentiment series,
  driven by ``PainPointInput.timestamp``. Empty when no input has a
  timestamp.
- ``tier_mix`` — fraction of supporting evidence by source-tier (L1..L5),
  driven by ``PainPointInput.source_tier``. Empty when no input has a
  tier (no synthetic L5 default — we tell the truth).

Neither field is synthesized; both degrade to empty when the loader can't
populate them.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field

from src.teams.social import TrendBucket


class PainPointEvidence(BaseModel):
    """One supporting evidence row for a pain point."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    excerpt: str
    sentiment: float = 0.0


class PainPoint(BaseModel):
    """One ranked pain point for the PM dashboard."""

    model_config = ConfigDict(extra="forbid")

    pain_point_id: str
    title: str
    audience_segment: str
    volume: int
    avg_sentiment: float
    references: list[str] = Field(default_factory=list)
    evidence: list[PainPointEvidence] = Field(default_factory=list)
    daily_buckets: list[TrendBucket] = Field(default_factory=list)
    tier_mix: dict[str, float] = Field(default_factory=dict)


@dataclass
class PainPointInput:
    """Input record for the aggregator — typically a Pass-4 extraction
    (sentiment / conflict_candidate / interview_q).

    ``timestamp`` + ``source_tier`` are optional. When the loader can fill
    them (graph mode pulls them from the underlying Post node + the
    annotation's ``ingest_iso`` / ``t_valid_from`` properties), the
    aggregator populates ``daily_buckets`` + ``tier_mix`` on the
    resulting PainPoint. When the loader can't, those fields stay empty
    rather than synthesized.
    """

    label: str                # e.g., "tuition_anxiety", "interview_logistics"
    audience_segment: str     # e.g., "applicants", "current_students"
    sentiment: float          # -1 (most negative) → 1 (most positive)
    source_id: str            # post_id / claim_id with provenance
    excerpt: str = ""
    timestamp: datetime | None = None
    source_tier: str | None = None
    cluster_id: str | None = None       # populated when the loader joins
                                        # Post → IN_CLUSTER → Cluster
    cluster_label: str | None = None    # human-friendly cluster name


def compute_pain_points(
    inputs: Iterable[PainPointInput],
    *,
    min_volume: int = 1,
    trend_window_days: int = 30,
    as_of: datetime | None = None,
) -> list[PainPoint]:
    """Aggregate Pass-4 inputs into PainPoints, ranked by volume (desc)
    then |sentiment| (desc) to surface the loudest negatives first.

    Each PainPoint also carries a ``daily_buckets`` series (one entry per
    distinct day in the last ``trend_window_days``) and a ``tier_mix``
    (fraction of supporting evidence per L1..L5 tier). Both are honestly
    empty when no input row carries a timestamp / tier respectively.
    """

    materialized = list(inputs)
    by_key: dict[tuple[str, str], list[PainPointInput]] = {}
    for item in materialized:
        key = (item.label, item.audience_segment)
        by_key.setdefault(key, []).append(item)

    end = as_of or datetime.now(UTC)
    window_start = end - timedelta(days=trend_window_days)

    out: list[PainPoint] = []
    for (label, segment), bucket in by_key.items():
        if len(bucket) < min_volume:
            continue
        avg_sentiment = sum(i.sentiment for i in bucket) / len(bucket)
        evidence = [
            PainPointEvidence(
                source_id=i.source_id, excerpt=i.excerpt[:280],
                sentiment=i.sentiment,
            )
            for i in bucket[:5]
        ]
        daily_buckets = _bucket_by_day(
            bucket, window_start=window_start, window_end=end,
        )
        tier_mix = _tier_mix(bucket)
        out.append(PainPoint(
            pain_point_id=f"pp:{label}:{segment}",
            title=_humanize_label(label),
            audience_segment=segment,
            volume=len(bucket),
            avg_sentiment=avg_sentiment,
            references=list({i.source_id for i in bucket}),
            evidence=evidence,
            daily_buckets=daily_buckets,
            tier_mix=tier_mix,
        ))

    out.sort(
        key=lambda p: (p.volume, abs(p.avg_sentiment)),
        reverse=True,
    )
    return out


def _bucket_by_day(
    items: list[PainPointInput], *, window_start: datetime, window_end: datetime,
) -> list[TrendBucket]:
    """Group items by day within the window. Returns a list of TrendBucket
    sorted ascending by date. Returns empty when no item has a timestamp.
    """

    per_day: dict[str, list[float]] = {}
    for it in items:
        if it.timestamp is None:
            continue
        # Normalize to UTC for window comparison; treat naive as UTC.
        ts = it.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        if ts < window_start or ts > window_end:
            continue
        day = ts.date().isoformat()
        per_day.setdefault(day, []).append(it.sentiment)
    if not per_day:
        return []
    return [
        TrendBucket(
            date=day,
            volume=len(sents),
            avg_sentiment=sum(sents) / len(sents),
        )
        for day, sents in sorted(per_day.items())
    ]


def _tier_mix(items: list[PainPointInput]) -> dict[str, float]:
    """Per-tier fraction across items with a known source_tier. When no
    items have a tier, returns an empty dict (the UI then omits the
    tier-mix bar rather than rendering fake data).
    """

    counts: dict[str, int] = {}
    total = 0
    for it in items:
        if not it.source_tier:
            continue
        counts[it.source_tier] = counts.get(it.source_tier, 0) + 1
        total += 1
    if total == 0:
        return {}
    return {tier: count / total for tier, count in counts.items()}


def _humanize_label(label: str) -> str:
    return " ".join(w.capitalize() for w in label.replace("_", " ").split())


@dataclass
class ClusterContribution:
    """One contributing cluster for a pain point. Lives at the input
    layer; the route maps it to the Pydantic ``ClusterContribution``
    response model."""

    cluster_id: str
    label: str
    count: int


def compute_top_clusters(
    inputs: Iterable[PainPointInput],
    *,
    top_n: int = 5,
) -> list[ClusterContribution]:
    """Group inputs by ``cluster_id`` and return the top-N most common
    clusters. Inputs without a ``cluster_id`` are excluded entirely
    (no synthetic ``"unknown"`` bucket). Returns an empty list when no
    input row has a cluster mapping.
    """

    counts: dict[str, tuple[str, int]] = {}
    for it in inputs:
        if not it.cluster_id:
            continue
        prev = counts.get(it.cluster_id)
        label = it.cluster_label or it.cluster_id
        if prev is None:
            counts[it.cluster_id] = (label, 1)
        else:
            counts[it.cluster_id] = (prev[0] or label, prev[1] + 1)
    if not counts:
        return []
    rows = [
        ClusterContribution(cluster_id=cid, label=label, count=n)
        for cid, (label, n) in counts.items()
    ]
    rows.sort(key=lambda r: r.count, reverse=True)
    return rows[:top_n]


__all__ = [
    "ClusterContribution",
    "PainPoint",
    "PainPointEvidence",
    "PainPointInput",
    "compute_pain_points",
    "compute_top_clusters",
]
