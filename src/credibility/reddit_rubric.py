from __future__ import annotations

import math

from src.credibility.api import RedditFeatures, Score


class RedditRubric:
    """V1 hand-weighted Reddit credibility rubric per ADR-008.

    Score formula:
        weighted = sum(feature_weight * normalized_feature)
        clipped  = clip(weighted, 0, 1)
        final    = clipped * 2 ** (-months_inactive / 12)
    """

    rubric_name = "reddit_v1"

    POST_CAP: int = 1000
    COMMENT_CAP: int = 5000
    UPVOTE_CAP: int = 50_000
    ACCOUNT_AGE_CAP: float = 2.0          # years
    GILDED_CAP: int = 50
    PRESCIENT_CAP: int = 20

    W_POST: float = 0.10
    W_COMMENT: float = 0.10
    W_UPVOTE: float = 0.15
    W_ACCOUNT_AGE: float = 0.10
    W_C2P_RATIO: float = 0.05
    W_ON_TOPIC: float = 0.20
    W_SOCKPUPPET: float = -0.10
    W_GILDED: float = 0.05
    W_PRESCIENT: float = 0.15
    INACTIVITY_HALF_LIFE_MONTHS: float = 12.0

    def score(self, f: RedditFeatures) -> Score:
        contrib: dict[str, float] = {}

        contrib["post_count"] = self.W_POST * _log_norm(f.post_count, self.POST_CAP)
        contrib["comment_count"] = self.W_COMMENT * _log_norm(
            f.comment_count, self.COMMENT_CAP,
        )
        contrib["upvote_total"] = self.W_UPVOTE * _log_norm(
            max(0, f.upvote_total), self.UPVOTE_CAP,
        )
        contrib["account_age_years"] = self.W_ACCOUNT_AGE * _linear_norm(
            f.account_age_years, self.ACCOUNT_AGE_CAP,
        )
        contrib["comment_to_post_ratio"] = self.W_C2P_RATIO * _clip01(
            f.comment_to_post_ratio,
        )
        contrib["on_topic_ratio"] = self.W_ON_TOPIC * _clip01(f.on_topic_ratio)
        contrib["sockpuppet_penalty"] = self.W_SOCKPUPPET * _clip01(
            f.sockpuppet_penalty,
        )
        contrib["gilded_bonus"] = self.W_GILDED * _linear_norm(
            f.gilded_count, self.GILDED_CAP,
        )
        contrib["prescient_correct_count"] = self.W_PRESCIENT * _linear_norm(
            f.prescient_correct_count, self.PRESCIENT_CAP,
        )

        raw = sum(contrib.values())
        clipped = max(0.0, min(1.0, raw))
        decay = 2.0 ** (-max(0.0, f.months_inactive) / self.INACTIVITY_HALF_LIFE_MONTHS)
        final = clipped * decay

        return Score(
            user_id=f.user_id,
            raw_score=raw,
            credibility=final,
            contributions=contrib,
            rubric=self.rubric_name,
        )


def _log_norm(value: float, cap: float) -> float:
    if cap <= 0:
        return 0.0
    clamped = max(0.0, min(float(value), float(cap)))
    return math.log1p(clamped) / math.log1p(float(cap))


def _linear_norm(value: float, cap: float) -> float:
    if cap <= 0:
        return 0.0
    return max(0.0, min(1.0, float(value) / float(cap)))


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
