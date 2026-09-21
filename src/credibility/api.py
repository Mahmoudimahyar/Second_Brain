from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Score:
    user_id: str
    raw_score: float          # weighted sum prior to clip + inactivity decay
    credibility: float        # final ∈ [0, 1]
    contributions: dict[str, float]   # per-feature weighted contribution
    rubric: str               # "reddit_v1" or "sdn_v1"


@dataclass(frozen=True)
class RedditFeatures:
    user_id: str
    post_count: int
    comment_count: int
    upvote_total: int
    account_age_years: float
    comment_to_post_ratio: float
    on_topic_ratio: float
    sockpuppet_penalty: float           # [0, 1] — 0 = no penalty, 1 = max
    gilded_count: int
    prescient_correct_count: int
    months_inactive: float = 0.0


@dataclass(frozen=True)
class SDNFeatures:
    user_id: str
    post_count: int
    account_age_proxy_years: float
    comment_to_post_ratio: float
    on_topic_ratio: float
    megathread_participation: int
    longevity_months: float
    prescient_correct_count: int
    months_inactive: float = 0.0
