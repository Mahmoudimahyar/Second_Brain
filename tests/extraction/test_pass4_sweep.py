"""Tests for `src.extraction.pass4_sweep.run_pass4_sweep`."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from src.extraction.cache import ExtractionCache
from src.extraction.pass4_sweep import (
    Pass4Input,
    Pass4Result,
    run_pass4_sweep,
    summarize,
)
from src.gateway import MockProvider, ModelGateway, TaskID
from src.observability import AuditLog


def _utc(year: int, month: int = 1, day: int = 1) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


def _sentiment_fixture(_p: str) -> str:
    return json.dumps({
        "verdict": "positive", "confidence": 0.9,
        "target_entities": ["school:nyu"],
        "reasoning": "Author is enthusiastic.",
    })


def _interview_q_fixture(_p: str) -> str:
    return json.dumps({
        "questions": [{
            "text": "Why our school?", "school_mention": "NYU",
            "year": 2024, "advice_given": None,
        }],
        "confidence": 0.8,
    })


def _conflict_fixture(_p: str) -> str:
    return json.dumps({
        "contains_candidate": True,
        "claim_subject": "NYU", "claim_predicate": "tuition_resident",
        "claim_value": "42000", "cycle_year": "2024-25",
        "confidence": 0.7,
    })


def _gateway_with(fixture_map: dict[TaskID, object]) -> ModelGateway:
    gw = ModelGateway()
    for task, fixture in fixture_map.items():
        gw.register(task, MockProvider(fixture=fixture))  # type: ignore[arg-type]
    return gw


def test_filtered_input_yields_filter_only_result(tmp_path: Path) -> None:
    cache = ExtractionCache(sqlite_path=tmp_path / "c.db")
    gw = _gateway_with({TaskID.PASS4_SENTIMENT: _sentiment_fixture})
    inputs = [Pass4Input(post_id="p1", text="", author=None)]

    results = list(run_pass4_sweep(
        inputs, tasks=("sentiment",), gateway=gw, cache=cache,
    ))

    assert len(results) == 1
    assert results[0].filter_decision.keep is False
    assert results[0].sentiment is None
    assert results[0].nodes == []


def test_kept_input_runs_sentiment_and_emits_annotation(tmp_path: Path) -> None:
    cache = ExtractionCache(sqlite_path=tmp_path / "c.db")
    gw = _gateway_with({TaskID.PASS4_SENTIMENT: _sentiment_fixture})
    inputs = [Pass4Input(
        post_id="reddit_post:abc",
        text="I love NYU College of Dentistry so much! Best decision ever.",
        author="alice", created_utc=_utc(2024, 5, 1),
    )]

    results = list(run_pass4_sweep(
        inputs, tasks=("sentiment",), gateway=gw, cache=cache,
    ))

    r = results[0]
    assert r.filter_decision.keep is True
    assert r.sentiment is not None
    assert r.sentiment.parsed is not None
    sentiment_nodes = [n for n in r.nodes if n.label == "SentimentAnnotation"]
    assert len(sentiment_nodes) == 1
    assert sentiment_nodes[0].properties["verdict"] == "positive"
    annotate_edges = [e for e in r.edges if e.label == "ANNOTATES"]
    assert annotate_edges[0].to_id == "reddit_post:abc"


def test_interview_q_emits_one_node_per_question(tmp_path: Path) -> None:
    cache = ExtractionCache(sqlite_path=tmp_path / "c.db")
    gw = _gateway_with({TaskID.PASS4_INTERVIEW_Q: _interview_q_fixture})
    inputs = [Pass4Input(
        post_id="reddit_post:abc",
        text="They asked: Why our school? I said best programs.",
        author="alice", mentions_entity=True,
    )]

    results = list(run_pass4_sweep(
        inputs, tasks=("interview_q",), gateway=gw, cache=cache,
    ))

    r = results[0]
    iq_nodes = [n for n in r.nodes if n.label == "InterviewQuestion"]
    assert len(iq_nodes) == 1
    assert iq_nodes[0].properties["text"] == "Why our school?"
    assert iq_nodes[0].properties["school_mention"] == "NYU"
    reported_at = [e for e in r.edges if e.label == "REPORTED_AT"]
    assert reported_at[0].to_id == "reddit_post:abc"


def test_conflict_candidate_emits_claim_node(tmp_path: Path) -> None:
    cache = ExtractionCache(sqlite_path=tmp_path / "c.db")
    gw = _gateway_with({TaskID.PASS4_CONFLICT_CANDIDATE: _conflict_fixture})
    inputs = [Pass4Input(
        post_id="reddit_post:abc",
        text="Heard NYU resident tuition is around $42k this year, true?",
        author="alice", mentions_entity=True,
    )]

    results = list(run_pass4_sweep(
        inputs, tasks=("conflict_candidate",), gateway=gw, cache=cache,
    ))

    r = results[0]
    claim_nodes = [n for n in r.nodes if n.label == "Claim"]
    assert len(claim_nodes) == 1
    assert claim_nodes[0].properties["predicate"] == "tuition_resident"
    assert claim_nodes[0].properties["value"] == "42000"


def test_multi_task_dispatch(tmp_path: Path) -> None:
    cache = ExtractionCache(sqlite_path=tmp_path / "c.db")
    gw = _gateway_with({
        TaskID.PASS4_SENTIMENT: _sentiment_fixture,
        TaskID.PASS4_INTERVIEW_Q: _interview_q_fixture,
        TaskID.PASS4_CONFLICT_CANDIDATE: _conflict_fixture,
    })
    inputs = [Pass4Input(
        post_id="reddit_post:abc",
        text="Loved NYU! They asked: Why our school? Tuition is $42k.",
        author="alice", mentions_entity=True,
    )]

    results = list(run_pass4_sweep(
        inputs, gateway=gw, cache=cache,
        tasks=("sentiment", "interview_q", "conflict_candidate"),
    ))

    r = results[0]
    assert r.sentiment is not None
    assert r.interview_q is not None
    assert r.conflict_candidate is not None
    node_labels = {n.label for n in r.nodes}
    assert "SentimentAnnotation" in node_labels
    assert "InterviewQuestion" in node_labels
    assert "Claim" in node_labels


def test_summarize_aggregates_metrics(tmp_path: Path) -> None:
    cache = ExtractionCache(sqlite_path=tmp_path / "c.db")
    gw = _gateway_with({TaskID.PASS4_SENTIMENT: _sentiment_fixture})

    inputs = [
        Pass4Input(post_id="kept",
                   text="Love NYU! What a great school.", author="a"),
        Pass4Input(post_id="filtered_empty", text="", author="a"),
        Pass4Input(post_id="filtered_bot", text="hello", author="AutoModerator"),
    ]

    results = list(run_pass4_sweep(
        inputs, tasks=("sentiment",), gateway=gw, cache=cache,
    ))
    s = summarize(results)

    assert s.total_inputs == 3
    assert s.filtered_out == 2
    assert s.processed == 1
    assert s.sentiment_count == 1


def test_warm_sweep_cache_hits(tmp_path: Path) -> None:
    cache = ExtractionCache(sqlite_path=tmp_path / "c.db")
    call_count = {"n": 0}

    def counting(_p: str) -> str:
        call_count["n"] += 1
        return _sentiment_fixture(_p)

    gw = _gateway_with({TaskID.PASS4_SENTIMENT: counting})
    inputs = [Pass4Input(post_id=f"p{i}",
                          text="Love it! Best school NYU.",
                          author="a") for i in range(3)]

    cold = list(run_pass4_sweep(
        inputs, tasks=("sentiment",), gateway=gw, cache=cache,
    ))
    warm = list(run_pass4_sweep(
        inputs, tasks=("sentiment",), gateway=gw, cache=cache,
    ))

    # All 3 inputs share the same text → same cache key. Cold sweep makes
    # 1 call (subsequent posts hit cache). Warm sweep makes 0 calls.
    cold_summary = summarize(cold)
    warm_summary = summarize(warm)
    assert cold_summary.cache_hits >= 2     # 2 of 3 hit cache (same text)
    assert warm_summary.cache_hits == 3
    assert warm_summary.total_cost_usd == 0.0


def test_audit_log_records_each_task_call(tmp_path: Path) -> None:
    cache = ExtractionCache(sqlite_path=tmp_path / "c.db")
    audit = AuditLog(sqlite_path=tmp_path / "a.db")
    gw = _gateway_with({TaskID.PASS4_SENTIMENT: _sentiment_fixture})
    inputs = [Pass4Input(post_id="p1",
                          text="I love NYU College of Dentistry.",
                          author="a")]

    list(run_pass4_sweep(
        inputs, tasks=("sentiment",), gateway=gw, cache=cache, audit=audit,
    ))

    rows = audit.query(kind="extraction")
    assert len(rows) == 1
    assert rows[0].ttl_pinned == 3600
    assert rows[0].fields["model"] == "mock-v1"


def test_yields_lazily_one_at_a_time(tmp_path: Path) -> None:
    """`run_pass4_sweep` is a generator — large inputs don't OOM."""

    cache = ExtractionCache(sqlite_path=tmp_path / "c.db")
    gw = _gateway_with({TaskID.PASS4_SENTIMENT: _sentiment_fixture})

    def big_stream() -> object:
        yielded = 0
        while yielded < 5:
            yield Pass4Input(post_id=f"p{yielded}",
                              text="I love NYU College", author="a")
            yielded += 1

    gen = run_pass4_sweep(
        big_stream(), tasks=("sentiment",), gateway=gw, cache=cache,
    )
    first = next(gen)
    assert isinstance(first, Pass4Result)


def test_no_node_emitted_when_conflict_candidate_false(tmp_path: Path) -> None:
    cache = ExtractionCache(sqlite_path=tmp_path / "c.db")

    def no_conflict(_p: str) -> str:
        return json.dumps({
            "contains_candidate": False,
            "claim_subject": None, "claim_predicate": None,
            "claim_value": None, "cycle_year": None,
            "confidence": 1.0,
        })

    gw = _gateway_with({TaskID.PASS4_CONFLICT_CANDIDATE: no_conflict})
    inputs = [Pass4Input(post_id="p1",
                          text="Just had a great study session at the library!",
                          author="a")]

    results = list(run_pass4_sweep(
        inputs, tasks=("conflict_candidate",), gateway=gw, cache=cache,
    ))

    claim_nodes = [n for n in results[0].nodes if n.label == "Claim"]
    assert claim_nodes == []
