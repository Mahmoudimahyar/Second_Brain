"""Tests for `src.credibility` rubrics (ADR-008)."""

from __future__ import annotations

import dataclasses

import pytest

from src.credibility import RedditFeatures, RedditRubric, SDNFeatures, SDNRubric
from src.credibility.api import Score


def _reddit_zeros(user_id: str = "u") -> RedditFeatures:
    return RedditFeatures(
        user_id=user_id, post_count=0, comment_count=0, upvote_total=0,
        account_age_years=0, comment_to_post_ratio=0, on_topic_ratio=0,
        sockpuppet_penalty=0, gilded_count=0, prescient_correct_count=0,
        months_inactive=0,
    )


def _sdn_zeros(user_id: str = "u") -> SDNFeatures:
    return SDNFeatures(
        user_id=user_id, post_count=0, account_age_proxy_years=0,
        comment_to_post_ratio=0, on_topic_ratio=0, megathread_participation=0,
        longevity_months=0, prescient_correct_count=0, months_inactive=0,
    )


def test_reddit_rubric_zero_features_scores_zero() -> None:
    s = RedditRubric().score(_reddit_zeros())
    assert s.credibility == pytest.approx(0.0)
    assert s.rubric == "reddit_v1"


def test_reddit_rubric_max_features_scores_near_one() -> None:
    f = RedditFeatures(
        user_id="u",
        post_count=10_000,           # > cap; saturates
        comment_count=50_000,
        upvote_total=500_000,
        account_age_years=10,
        comment_to_post_ratio=1.0,
        on_topic_ratio=1.0,
        sockpuppet_penalty=0.0,
        gilded_count=200,
        prescient_correct_count=100,
        months_inactive=0,
    )
    s = RedditRubric().score(f)

    # 0.10 + 0.10 + 0.15 + 0.10 + 0.05 + 0.20 + 0.05 + 0.15 = 0.90
    # (sockpuppet_penalty = 0 contributes 0)
    assert s.raw_score == pytest.approx(0.90, rel=1e-3)
    assert s.credibility == pytest.approx(0.90, rel=1e-3)


def test_reddit_sockpuppet_penalty_subtracts() -> None:
    f = RedditFeatures(
        user_id="u",
        post_count=100, comment_count=200, upvote_total=1000,
        account_age_years=1, comment_to_post_ratio=0.5,
        on_topic_ratio=0.8, sockpuppet_penalty=0.0,
        gilded_count=0, prescient_correct_count=0,
        months_inactive=0,
    )
    clean = RedditRubric().score(f)
    cheaty = RedditRubric().score(
        RedditFeatures(
            user_id="u", post_count=f.post_count, comment_count=f.comment_count,
            upvote_total=f.upvote_total, account_age_years=f.account_age_years,
            comment_to_post_ratio=f.comment_to_post_ratio,
            on_topic_ratio=f.on_topic_ratio, sockpuppet_penalty=1.0,
            gilded_count=f.gilded_count, prescient_correct_count=f.prescient_correct_count,
            months_inactive=f.months_inactive,
        ),
    )

    assert cheaty.credibility < clean.credibility
    assert clean.raw_score - cheaty.raw_score == pytest.approx(0.10)


def test_reddit_inactivity_half_life_at_12_months() -> None:
    f_now = RedditFeatures(
        user_id="u",
        post_count=10_000, comment_count=50_000, upvote_total=500_000,
        account_age_years=10, comment_to_post_ratio=1.0, on_topic_ratio=1.0,
        sockpuppet_penalty=0.0, gilded_count=200, prescient_correct_count=100,
        months_inactive=0,
    )
    f_year = RedditFeatures(**{**f_now.__dict__, "months_inactive": 12})
    f_two = RedditFeatures(**{**f_now.__dict__, "months_inactive": 24})

    now = RedditRubric().score(f_now)
    year = RedditRubric().score(f_year)
    two = RedditRubric().score(f_two)

    # half-life 12 months
    assert year.credibility == pytest.approx(now.credibility / 2, rel=1e-6)
    assert two.credibility == pytest.approx(now.credibility / 4, rel=1e-6)


def test_reddit_clip_to_zero_when_only_sockpuppet_penalty() -> None:
    f = RedditFeatures(
        user_id="u",
        post_count=0, comment_count=0, upvote_total=0,
        account_age_years=0, comment_to_post_ratio=0, on_topic_ratio=0,
        sockpuppet_penalty=1.0, gilded_count=0, prescient_correct_count=0,
        months_inactive=0,
    )
    s = RedditRubric().score(f)
    assert s.raw_score == pytest.approx(-0.10)
    assert s.credibility == pytest.approx(0.0)


def test_reddit_on_topic_ratio_is_strongest_signal() -> None:
    # 0.20 weight — strongest among non-upvote features. Verify by comparing.
    base = RedditFeatures(
        user_id="u", post_count=0, comment_count=0, upvote_total=0,
        account_age_years=0, comment_to_post_ratio=0, on_topic_ratio=0,
        sockpuppet_penalty=0, gilded_count=0, prescient_correct_count=0,
        months_inactive=0,
    )
    base_score = RedditRubric().score(base).credibility
    boosted = RedditRubric().score(
        RedditFeatures(**{**base.__dict__, "on_topic_ratio": 1.0}),
    )
    other = RedditRubric().score(
        RedditFeatures(**{**base.__dict__, "comment_to_post_ratio": 1.0}),
    )

    assert boosted.credibility - base_score == pytest.approx(0.20)
    assert other.credibility - base_score == pytest.approx(0.05)
    assert boosted.credibility > other.credibility


def test_sdn_rubric_zero_features_scores_zero() -> None:
    s = SDNRubric().score(_sdn_zeros())
    assert s.credibility == pytest.approx(0.0)
    assert s.rubric == "sdn_v1"


def test_sdn_rubric_max_features_scores_correct_sum() -> None:
    f = SDNFeatures(
        user_id="u",
        post_count=10_000, account_age_proxy_years=10,
        comment_to_post_ratio=1.0, on_topic_ratio=1.0,
        megathread_participation=200, longevity_months=120,
        prescient_correct_count=100, months_inactive=0,
    )
    s = SDNRubric().score(f)
    # 0.15 + 0.10 + 0.05 + 0.25 + 0.15 + 0.15 + 0.15 = 1.00
    assert s.raw_score == pytest.approx(1.00, rel=1e-3)
    assert s.credibility == pytest.approx(1.00, rel=1e-3)


def test_sdn_on_topic_carries_more_weight_than_reddit() -> None:
    # SDN weight = 0.25 vs Reddit 0.20 — verifies the ADR-008 explicit choice.
    rb = RedditRubric()
    sb = SDNRubric()
    assert sb.W_ON_TOPIC > rb.W_ON_TOPIC
    assert pytest.approx(0.25) == sb.W_ON_TOPIC
    assert pytest.approx(0.20) == rb.W_ON_TOPIC


def test_sdn_has_no_sockpuppet_penalty() -> None:
    s = SDNRubric().score(_sdn_zeros())
    # SDN rubric contributions must NOT include a sockpuppet term (deferred per ADR-008).
    assert "sockpuppet_penalty" not in s.contributions


def test_sdn_inactivity_half_life() -> None:
    f_now = SDNFeatures(
        user_id="u", post_count=10_000, account_age_proxy_years=10,
        comment_to_post_ratio=1.0, on_topic_ratio=1.0,
        megathread_participation=200, longevity_months=120,
        prescient_correct_count=100, months_inactive=0,
    )
    f_year = SDNFeatures(**{**f_now.__dict__, "months_inactive": 12})

    now = SDNRubric().score(f_now)
    year = SDNRubric().score(f_year)
    assert year.credibility == pytest.approx(now.credibility / 2, rel=1e-6)


def test_score_contains_per_feature_contributions() -> None:
    f = RedditFeatures(
        user_id="alice",
        post_count=10, comment_count=20, upvote_total=100,
        account_age_years=1, comment_to_post_ratio=0.4, on_topic_ratio=0.7,
        sockpuppet_penalty=0, gilded_count=2, prescient_correct_count=3,
        months_inactive=0,
    )
    s = RedditRubric().score(f)

    expected_keys = {
        "post_count", "comment_count", "upvote_total", "account_age_years",
        "comment_to_post_ratio", "on_topic_ratio", "sockpuppet_penalty",
        "gilded_bonus", "prescient_correct_count",
    }
    assert set(s.contributions.keys()) == expected_keys
    assert s.user_id == "alice"


def test_score_dataclass_is_frozen() -> None:
    s = Score(user_id="u", raw_score=0, credibility=0,
              contributions={}, rubric="reddit_v1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.credibility = 1.0  # type: ignore[misc]


def test_credibility_clips_to_unit_interval() -> None:
    # Even at max features without inactivity, Reddit caps at 0.90 (sockpuppet
    # weight is -0.10 so the positive weights sum to 0.90). SDN caps at 1.00.
    # Test that values are always in [0, 1].
    for rubric, features in (
        (RedditRubric(), RedditFeatures(
            user_id="u", post_count=99999, comment_count=99999, upvote_total=999999,
            account_age_years=99, comment_to_post_ratio=10.0, on_topic_ratio=10.0,
            sockpuppet_penalty=-5.0, gilded_count=99999, prescient_correct_count=99999,
            months_inactive=0,
        )),
        (SDNRubric(), SDNFeatures(
            user_id="u", post_count=99999, account_age_proxy_years=99,
            comment_to_post_ratio=10.0, on_topic_ratio=10.0,
            megathread_participation=99999, longevity_months=99999,
            prescient_correct_count=99999, months_inactive=0,
        )),
    ):
        s = rubric.score(features)
        assert 0.0 <= s.credibility <= 1.0
