from __future__ import annotations

from src.credibility.api import Score, SDNFeatures
from src.credibility.reddit_rubric import _clip01, _linear_norm, _log_norm


class SDNRubric:
    """V1 hand-weighted SDN credibility rubric per ADR-008 §"SDN rubric (7 features)".

    No upvote / karma signal; on_topic_ratio carries more weight (0.25 vs 0.20)
    and megathread_participation + longevity_months take the upvote slot.
    """

    rubric_name = "sdn_v1"

    POST_CAP: int = 1000
    AGE_CAP: float = 2.0                 # years
    MEGATHREAD_CAP: int = 50
    LONGEVITY_CAP: float = 60.0          # months
    PRESCIENT_CAP: int = 20

    W_POST: float = 0.15
    W_ACCOUNT_AGE: float = 0.10
    W_C2P_RATIO: float = 0.05
    W_ON_TOPIC: float = 0.25
    W_MEGATHREAD: float = 0.15
    W_LONGEVITY: float = 0.15
    W_PRESCIENT: float = 0.15
    INACTIVITY_HALF_LIFE_MONTHS: float = 12.0

    def score(self, f: SDNFeatures) -> Score:
        contrib: dict[str, float] = {}

        contrib["post_count"] = self.W_POST * _log_norm(f.post_count, self.POST_CAP)
        contrib["account_age_proxy_years"] = self.W_ACCOUNT_AGE * _linear_norm(
            f.account_age_proxy_years, self.AGE_CAP,
        )
        contrib["comment_to_post_ratio"] = self.W_C2P_RATIO * _clip01(
            f.comment_to_post_ratio,
        )
        contrib["on_topic_ratio"] = self.W_ON_TOPIC * _clip01(f.on_topic_ratio)
        contrib["megathread_participation"] = self.W_MEGATHREAD * _linear_norm(
            f.megathread_participation, self.MEGATHREAD_CAP,
        )
        contrib["longevity_months"] = self.W_LONGEVITY * _linear_norm(
            f.longevity_months, self.LONGEVITY_CAP,
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
