"""Tests for `src.extraction.utility_filter.filter_post` (A-057, GAP-035)."""

from __future__ import annotations

from src.extraction.utility_filter import FilterContext, filter_post


def _ctx(**kwargs: object) -> FilterContext:
    defaults: dict = {
        "text": "This is a normal post body about dental school.",
        "author": "alice",
        "is_reply": False,
        "is_crosspost": False,
        "duplicate_of": None,
        "mentions_entity": False,
        "score": 1,
    }
    defaults.update(kwargs)
    return FilterContext(**defaults)  # type: ignore[arg-type]


def test_kept_post_with_question_mark() -> None:
    d = filter_post(_ctx(text="What's a good DAT prep book?"))
    assert d.keep is True
    assert d.reason == "kept"


def test_kept_post_with_sentiment_marker() -> None:
    d = filter_post(_ctx(text="I love Kaplan."))
    assert d.keep is True


def test_kept_post_when_mentions_entity_even_low_signal() -> None:
    d = filter_post(_ctx(text="NYU", mentions_entity=True))
    assert d.keep is True


def test_drops_deleted_author() -> None:
    d = filter_post(_ctx(author=None))
    assert d.keep is False
    assert d.reason == "no_author_deleted_or_removed"


def test_drops_bot_automoderator() -> None:
    d = filter_post(_ctx(author="AutoModerator"))
    assert d.keep is False
    assert d.reason == "bot_author"


def test_drops_named_bot() -> None:
    assert filter_post(_ctx(author="my-Bot")).keep is False
    assert filter_post(_ctx(author="something_bot_")).keep is False


def test_drops_very_short_reply_without_entity() -> None:
    d = filter_post(_ctx(text="thanks!", is_reply=True))
    assert d.keep is False
    assert d.reason == "very_short_reply_no_entity"


def test_keeps_short_reply_when_mentions_entity() -> None:
    # prescient_correct preservation (A-032).
    d = filter_post(_ctx(text="NYU", is_reply=True, mentions_entity=True))
    assert d.keep is True


def test_drops_crosspost_duplicate() -> None:
    d = filter_post(_ctx(is_crosspost=True, duplicate_of="reddit_post:x"))
    assert d.keep is False
    assert d.reason == "crosspost_duplicate"


def test_drops_generic_post_without_entity_question_or_sentiment() -> None:
    d = filter_post(_ctx(
        text="I went for a walk today. It was sunny.",
        mentions_entity=False,
    ))
    assert d.keep is False
    assert d.reason == "generic_no_entity_no_question_no_sentiment"


def test_keeps_long_body_with_sentiment_marker() -> None:
    long_body = "Class is amazing and I really recommend the program highly."
    d = filter_post(_ctx(text=long_body))
    assert d.keep is True


def test_decision_includes_entity_flag() -> None:
    d = filter_post(_ctx(text="Look at NYU", mentions_entity=True))
    assert d.mentions_entity is True
