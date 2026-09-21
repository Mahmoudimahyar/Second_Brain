"""Tests for `src.extraction.pass4_runners` (FR-2.3 task runners)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticVE

from src.extraction.cache import ExtractionCache
from src.extraction.pass4_runners import (
    extract_conflict_candidate,
    extract_interview_questions,
    extract_sentiment,
)
from src.extraction.pass4_schemas import (
    ConflictCandidate,
    InterviewQuestionHarvest,
    Sentiment,
)
from src.gateway import MockProvider, ModelGateway, TaskID
from src.observability import AuditLog


def _gateway(fixture_fn: object) -> ModelGateway:
    provider = MockProvider(vendor="mock", model="mock-v1",
                            fixture=fixture_fn)  # type: ignore[arg-type]
    gw = ModelGateway()
    for task in (
        TaskID.PASS4_SENTIMENT,
        TaskID.PASS4_INTERVIEW_Q,
        TaskID.PASS4_CONFLICT_CANDIDATE,
    ):
        gw.register(task, provider)
    return gw


def _sentiment_fixture(_prompt: str) -> str:
    return json.dumps({
        "verdict": "positive",
        "confidence": 0.91,
        "target_entities": ["school:nyu"],
        "reasoning": "Author expresses excitement about NYU acceptance.",
    })


def _interview_q_fixture(_prompt: str) -> str:
    return json.dumps({
        "questions": [
            {"text": "Why our school over Harvard?",
             "school_mention": "NYU", "year": 2024,
             "advice_given": "Be specific about programs"},
        ],
        "confidence": 0.85,
    })


def _conflict_candidate_fixture(_prompt: str) -> str:
    return json.dumps({
        "contains_candidate": True,
        "claim_subject": "NYU College of Dentistry",
        "claim_predicate": "tuition_resident",
        "claim_value": "40000",
        "cycle_year": "2024-25",
        "confidence": 0.7,
    })


def test_sentiment_returns_parsed_schema(tmp_path: Path) -> None:
    cache = ExtractionCache(sqlite_path=tmp_path / "cache.db")
    gw = _gateway(_sentiment_fixture)

    outcome = extract_sentiment("I love NYU!", gateway=gw, cache=cache)

    assert outcome.error is None
    assert isinstance(outcome.parsed, Sentiment)
    assert outcome.parsed.verdict == "positive"
    assert outcome.parsed.confidence == pytest.approx(0.91)
    assert outcome.cache_hit is False


def test_interview_q_returns_parsed_schema(tmp_path: Path) -> None:
    cache = ExtractionCache(sqlite_path=tmp_path / "cache.db")
    gw = _gateway(_interview_q_fixture)

    outcome = extract_interview_questions(
        "They asked why this school over Harvard?", gateway=gw, cache=cache,
    )

    assert isinstance(outcome.parsed, InterviewQuestionHarvest)
    assert len(outcome.parsed.questions) == 1
    assert outcome.parsed.questions[0].school_mention == "NYU"


def test_conflict_candidate_returns_parsed_schema(tmp_path: Path) -> None:
    cache = ExtractionCache(sqlite_path=tmp_path / "cache.db")
    gw = _gateway(_conflict_candidate_fixture)

    outcome = extract_conflict_candidate(
        "I heard NYU tuition is $40k", gateway=gw, cache=cache,
    )

    assert isinstance(outcome.parsed, ConflictCandidate)
    assert outcome.parsed.contains_candidate is True
    assert outcome.parsed.claim_value == "40000"


def test_cache_hit_on_second_call(tmp_path: Path) -> None:
    cache = ExtractionCache(sqlite_path=tmp_path / "cache.db")
    call_count = {"n": 0}

    def counting_fixture(_p: str) -> str:
        call_count["n"] += 1
        return _sentiment_fixture(_p)

    gw = _gateway(counting_fixture)

    cold = extract_sentiment("Hello world", gateway=gw, cache=cache)
    warm = extract_sentiment("Hello world", gateway=gw, cache=cache)

    assert cold.cache_hit is False
    assert warm.cache_hit is True
    assert call_count["n"] == 1
    assert warm.cost_usd == 0.0


def test_empty_input_short_circuits(tmp_path: Path) -> None:
    cache = ExtractionCache(sqlite_path=tmp_path / "cache.db")
    gw = _gateway(_sentiment_fixture)

    outcome = extract_sentiment("   ", gateway=gw, cache=cache)

    assert outcome.parsed is None
    assert outcome.error == "empty input"
    assert outcome.cost_usd == 0.0


def test_no_provider_registered_returns_error(tmp_path: Path) -> None:
    cache = ExtractionCache(sqlite_path=tmp_path / "cache.db")
    empty_gw = ModelGateway()

    outcome = extract_sentiment("Hello", gateway=empty_gw, cache=cache)

    assert outcome.parsed is None
    assert outcome.error is not None
    assert "No provider configured" in outcome.error


def test_audit_log_records_extraction(tmp_path: Path) -> None:
    cache = ExtractionCache(sqlite_path=tmp_path / "cache.db")
    audit = AuditLog(sqlite_path=tmp_path / "audit.db")
    gw = _gateway(_sentiment_fixture)

    extract_sentiment("Hello", gateway=gw, cache=cache, audit=audit)

    rows = audit.query(kind="extraction")
    assert len(rows) == 1
    assert rows[0].ttl_pinned == 3600
    assert rows[0].fields["cache_hit"] is False
    assert rows[0].fields["model"] == "mock-v1"


def test_audit_log_records_cache_hit_separately(tmp_path: Path) -> None:
    cache = ExtractionCache(sqlite_path=tmp_path / "cache.db")
    audit = AuditLog(sqlite_path=tmp_path / "audit.db")
    gw = _gateway(_sentiment_fixture)

    extract_sentiment("Hello", gateway=gw, cache=cache, audit=audit)
    extract_sentiment("Hello", gateway=gw, cache=cache, audit=audit)

    rows = audit.query(kind="extraction")
    assert len(rows) == 2
    cache_hits = sorted(r.fields["cache_hit"] for r in rows)
    assert cache_hits == [False, True]


def test_invalid_json_response_yields_none_parsed(tmp_path: Path) -> None:
    cache = ExtractionCache(sqlite_path=tmp_path / "cache.db")
    gw = _gateway(lambda _p: "not valid json at all")

    outcome = extract_sentiment("Hello", gateway=gw, cache=cache)

    assert outcome.parsed is None
    assert outcome.cache_hit is False


def test_cache_key_changes_per_prompt_version_change(tmp_path: Path) -> None:
    """Distinct task IDs yield distinct cache keys, even for the same text."""

    cache = ExtractionCache(sqlite_path=tmp_path / "cache.db")
    gw = _gateway(_sentiment_fixture)

    extract_sentiment("Hello world", gateway=gw, cache=cache)
    sentiment_size = cache.size()

    # Same prompt, different task → cache should not collide
    gw2 = _gateway(_interview_q_fixture)
    extract_interview_questions("Hello world", gateway=gw2, cache=cache)

    assert cache.size() == sentiment_size + 1


def test_schema_extra_fields_rejected() -> None:
    """Schema's extra=forbid means a field not in the schema fails validation."""

    with pytest.raises(PydanticVE):
        Sentiment.model_validate({
            "verdict": "positive", "confidence": 0.5,
            "target_entities": [], "reasoning": "",
            "rogue_field": "x",
        })


def test_confidence_must_be_in_unit_interval() -> None:
    with pytest.raises(PydanticVE):
        Sentiment.model_validate({
            "verdict": "positive", "confidence": 1.5,
            "target_entities": [], "reasoning": "",
        })
    with pytest.raises(PydanticVE):
        Sentiment.model_validate({
            "verdict": "positive", "confidence": -0.1,
            "target_entities": [], "reasoning": "",
        })
