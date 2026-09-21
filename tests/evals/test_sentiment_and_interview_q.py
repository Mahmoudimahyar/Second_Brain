"""Tests for `evals.sentiment` and `evals.interview_q` eval harnesses.

Uses MockProvider so no LLM calls happen.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.interview_q import (
    GoldInterviewQ,
    _fuzzy_question_match,
)
from evals.interview_q import (
    evaluate as eval_iq,
)
from evals.interview_q import (
    load_gold as load_iq_gold,
)
from evals.sentiment import (
    GoldSentiment,
)
from evals.sentiment import (
    evaluate as eval_sentiment,
)
from evals.sentiment import (
    load_gold as load_sentiment_gold,
)
from src.gateway import MockProvider, ModelGateway, TaskID


def _seed_gateway(monkeypatch: pytest.MonkeyPatch, fixture_map: dict[TaskID, object]) -> None:
    """Replace `default_gateway` with one that uses fixtures."""

    def fake_default_gateway() -> ModelGateway:
        gw = ModelGateway()
        for task, fixture in fixture_map.items():
            gw.register(task, MockProvider(fixture=fixture))  # type: ignore[arg-type]
        return gw

    monkeypatch.setattr("evals.sentiment.default_gateway", fake_default_gateway)
    monkeypatch.setattr("evals.interview_q.default_gateway", fake_default_gateway)


def _positive_fixture(_p: str) -> str:
    return json.dumps({
        "verdict": "positive", "confidence": 0.9,
        "target_entities": [], "reasoning": "",
    })


def _iq_fixture(_p: str) -> str:
    return json.dumps({
        "questions": [{
            "text": "Why our school?", "school_mention": None,
            "year": None, "advice_given": None,
        }],
        "confidence": 0.9,
    })


def _empty_iq_fixture(_p: str) -> str:
    return json.dumps({"questions": [], "confidence": 1.0})


def test_sentiment_eval_perfect_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_gateway(monkeypatch, {TaskID.PASS4_SENTIMENT: _positive_fixture})
    gold = [GoldSentiment("I love NYU!", "positive", [])]

    res = eval_sentiment(gold, sqlite_path=tmp_path / "cache.db")

    assert res.total == 1
    assert res.correct == 1
    assert res.accuracy == 1.0
    assert res.passes_threshold(0.8)


def test_sentiment_eval_records_mismatches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_gateway(monkeypatch, {TaskID.PASS4_SENTIMENT: _positive_fixture})
    gold = [
        GoldSentiment("I love NYU!", "positive", []),
        GoldSentiment("Tufts rejected me", "negative", []),
    ]

    res = eval_sentiment(gold, sqlite_path=tmp_path / "cache.db")

    assert res.correct == 1
    assert res.accuracy == 0.5
    assert len(res.mismatches) == 1


def test_sentiment_load_gold(tmp_path: Path) -> None:
    path = tmp_path / "g.jsonl"
    path.write_text(
        '\n'.join([
            json.dumps({"text": "a", "expected_verdict": "positive",
                        "expected_target_entities": ["x"]}),
            json.dumps({"text": "b", "expected_verdict": "neutral",
                        "expected_target_entities": []}),
        ]),
        encoding="utf-8",
    )
    gold = load_sentiment_gold(path)
    assert len(gold) == 2
    assert gold[0].expected_verdict == "positive"


def test_fuzzy_question_match() -> None:
    assert _fuzzy_question_match("Why this school?", "Why this school?")
    assert _fuzzy_question_match(
        "Why our school over Harvard?", "Why our school over Harvard?",
    )
    # Substring direction
    assert _fuzzy_question_match("Why?", "tell me Why?")
    # Token overlap above threshold
    assert _fuzzy_question_match(
        "tell me about a leadership experience",
        "a leadership experience tell me about",
    )
    # No overlap
    assert not _fuzzy_question_match("foo bar", "completely different text here")


def test_interview_q_eval_with_matched_questions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_gateway(monkeypatch, {TaskID.PASS4_INTERVIEW_Q: _iq_fixture})
    gold = [
        GoldInterviewQ("They asked: Why our school?", ["Why our school?"]),
    ]

    res = eval_iq(gold, sqlite_path=tmp_path / "cache.db")

    assert res.matched_q == 1
    assert res.expected_q_total == 1
    assert res.predicted_q_total == 1
    assert res.f1 == pytest.approx(1.0)


def test_interview_q_eval_no_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_gateway(monkeypatch, {TaskID.PASS4_INTERVIEW_Q: _empty_iq_fixture})
    gold = [GoldInterviewQ("They asked: Why our school?", ["Why our school?"])]

    res = eval_iq(gold, sqlite_path=tmp_path / "cache.db")
    assert res.matched_q == 0
    assert res.recall == 0.0


def test_interview_q_load_gold(tmp_path: Path) -> None:
    path = tmp_path / "g.jsonl"
    path.write_text(
        json.dumps({
            "text": "Q: Why us? A: ...",
            "expected_questions": ["Why us?"],
        }) + "\n",
        encoding="utf-8",
    )
    gold = load_iq_gold(path)
    assert len(gold) == 1
    assert gold[0].expected_count == 1


def test_real_gold_files_load() -> None:
    base = Path(__file__).parent.parent.parent / "evals" / "gold"
    sentiment_path = base / "sentiment.jsonl"
    iq_path = base / "interview_q.jsonl"
    if sentiment_path.is_file():
        s = load_sentiment_gold(sentiment_path)
        assert len(s) >= 5
        for g in s:
            assert g.expected_verdict in {"positive", "negative", "neutral", "mixed"}
    if iq_path.is_file():
        i = load_iq_gold(iq_path)
        assert len(i) >= 5
