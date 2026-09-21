"""Tier-as-prior calibrated ranking (ADR-021 + ADR-007 + ADR-008, GAP-048/050).

The single place tier / recency / credibility / consistency combine:

    ranking_score = w_tier(tier) x w_rank(rank) x decay x credibility x consistency

`w_tier` is a **prior weight, not a hard pre-sort** — so a fresh, corroborated,
high-credibility L5 claim CAN outrank a stale L1 record (the minority-correct
case the lexicographic "tier-first" rule got wrong). Pure + deterministic given
inputs; the retrieval service feeds it `QueryResult`s via `rank_query_results`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from src.conflict.halo_table import decay
from src.retrieval.consistency import (
    DEFAULT_TIER_WEIGHTS,
    SourceClaim,
    consistency,
)

# Wikidata-style rank weight (ADR-021/ADR-007): preferred 1.0 / normal 0.5 / deprecated 0.0.
W_RANK: dict[str, float] = {"preferred": 1.0, "normal": 0.5, "deprecated": 0.0}


@dataclass(frozen=True)
class RankingWeights:
    w_tier: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_TIER_WEIGHTS),
    )
    w_rank: dict[str, float] = field(default_factory=lambda: dict(W_RANK))


DEFAULT_WEIGHTS = RankingWeights()


def ranking_score(
    *,
    source_tier: str,
    rank: str,
    decay_factor: float,
    credibility: float,
    consistency_factor: float,
    weights: RankingWeights = DEFAULT_WEIGHTS,
) -> float:
    """Combine the five signals into a single comparable score."""
    return (
        weights.w_tier.get(source_tier, 0.4)
        * weights.w_rank.get(rank, 0.5)
        * max(0.0, decay_factor)
        * max(0.0, credibility)
        * max(0.0, consistency_factor)
    )


class RankableResult(Protocol):
    """Structural (read-only) type the ranker needs (satisfied by `QueryResult`)."""

    @property
    def node_type(self) -> str: ...
    @property
    def source_tier(self) -> str: ...
    @property
    def rank(self) -> str: ...
    @property
    def t_valid_from(self) -> datetime | None: ...
    @property
    def properties(self) -> dict[str, Any]: ...


def _group_key(props: dict[str, Any]) -> tuple[str, str] | None:
    subj = props.get("subject_id") or props.get("school_id") or props.get("school")
    pred = props.get("predicate") or props.get("metric") or props.get("metric_name")
    if subj and pred:
        return (str(subj), str(pred))
    return None


def _value_of(props: dict[str, Any]) -> Any:
    for key in ("object_value", "value", "metric_value"):
        if key in props:
            return props[key]
    return None


def _credibility_of(props: dict[str, Any]) -> float:
    for key in ("user_credibility", "credibility", "author_credibility"):
        v = props.get(key)
        if isinstance(v, (int, float)):
            return float(v)
    return 1.0


def _halo_key(node_type: str, props: dict[str, Any]) -> str | None:
    return (
        props.get("predicate")
        or props.get("metric")
        or props.get("metric_name")
        or node_type
    )


def score_of(
    result: RankableResult, *, now: datetime, peers: Sequence[SourceClaim],
    weights: RankingWeights = DEFAULT_WEIGHTS,
) -> float:
    """Score a single result given its consistency peer set (may be empty)."""
    props = result.properties
    cred = _credibility_of(props)
    if len(peers) > 1:
        target = SourceClaim(
            value=_value_of(props), source_tier=result.source_tier, credibility=cred,
        )
        cons = consistency(target, peers, weights.w_tier)
    else:
        cons = 1.0
    d = decay(now, result.t_valid_from, _halo_key(result.node_type, props))
    return ranking_score(
        source_tier=result.source_tier, rank=result.rank, decay_factor=d,
        credibility=cred, consistency_factor=cons, weights=weights,
    )


def rank_query_results[R: RankableResult](
    results: Sequence[R], *, now: datetime, weights: RankingWeights = DEFAULT_WEIGHTS,
) -> list[R]:
    """Return `results` ordered by `ranking_score` desc (stable on ties).

    Cross-source `consistency` is computed within (subject, predicate) groups
    found in the result set; results outside any multi-member group get the
    neutral consistency 1.0.
    """
    groups: dict[tuple[str, str], list[R]] = {}
    for r in results:
        key = _group_key(r.properties)
        if key is not None:
            groups.setdefault(key, []).append(r)

    scored: list[float] = []
    for r in results:
        key = _group_key(r.properties)
        members = groups.get(key, []) if key is not None else []
        peers = [
            SourceClaim(
                value=_value_of(m.properties), source_tier=m.source_tier,
                credibility=_credibility_of(m.properties),
            )
            for m in members
        ]
        scored.append(score_of(r, now=now, peers=peers, weights=weights))

    order = sorted(range(len(results)), key=lambda i: (-scored[i], i))
    return [results[i] for i in order]
