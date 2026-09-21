"""Tests for V1.5b Phase 5 — `FeedbackLog` (ADR-018)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.extraction.feedback_log import FeedbackLog
from src.shared.errors import ErrorCode, StructuredError


@pytest.fixture
def log(tmp_path: Path) -> FeedbackLog:
    return FeedbackLog(sqlite_path=tmp_path / "engine.db")


def test_append_creates_entry(log: FeedbackLog) -> None:
    entry = log.append(
        corpus_id="corpus:dental",
        item_type="node_proposal",
        pattern="Sentiment:Frustration",
        verdict="accept",
        decided_by="mahyar",
        prompt_template_id="extract_sentiment",
    )
    assert entry.feedback_id.startswith("fb:")
    assert entry.verdict == "accept"
    assert entry.pattern_canonical == "sentiment:frustration"


def test_append_only_no_updates(log: FeedbackLog) -> None:
    entry = log.append(
        corpus_id="c1", item_type="node_proposal",
        pattern="X", verdict="accept", decided_by="m",
    )
    # Direct SQL UPDATE should fail because the trigger raises.
    with sqlite3.connect(log._sqlite_path) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE feedback_log SET verdict = 'reject' "
            "WHERE feedback_id = ?",
            (entry.feedback_id,),
        )


def test_append_only_no_deletes(log: FeedbackLog) -> None:
    entry = log.append(
        corpus_id="c1", item_type="node_proposal",
        pattern="X", verdict="accept", decided_by="m",
    )
    with sqlite3.connect(log._sqlite_path) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "DELETE FROM feedback_log WHERE feedback_id = ?",
            (entry.feedback_id,),
        )


def test_list_for_corpus_filters_by_verdict(log: FeedbackLog) -> None:
    log.append(
        corpus_id="c1", item_type="node_proposal",
        pattern="A", verdict="accept", decided_by="m",
    )
    log.append(
        corpus_id="c1", item_type="node_proposal",
        pattern="B", verdict="reject", decided_by="m",
    )
    log.append(
        corpus_id="c2", item_type="node_proposal",
        pattern="C", verdict="accept", decided_by="m",
    )
    accepts_c1 = log.list_for_corpus("c1", verdict="accept")
    assert {e.pattern for e in accepts_c1} == {"A"}


def test_list_for_corpus_filters_by_template(log: FeedbackLog) -> None:
    log.append(
        corpus_id="c1", item_type="np", pattern="A", verdict="accept",
        decided_by="m", prompt_template_id="t1",
    )
    log.append(
        corpus_id="c1", item_type="np", pattern="B", verdict="accept",
        decided_by="m", prompt_template_id="t2",
    )
    log.append(
        corpus_id="c1", item_type="np", pattern="C", verdict="accept",
        decided_by="m",
    )  # no template_id → applies to all
    for_t1 = log.list_for_corpus("c1", prompt_template_id="t1")
    patterns = {e.pattern for e in for_t1}
    assert patterns == {"A", "C"}


def test_count_per_corpus(log: FeedbackLog) -> None:
    log.append(corpus_id="c1", item_type="np", pattern="A",
               verdict="accept", decided_by="m")
    log.append(corpus_id="c1", item_type="np", pattern="B",
               verdict="reject", decided_by="m")
    log.append(corpus_id="c2", item_type="np", pattern="C",
               verdict="accept", decided_by="m")
    assert log.count("c1") == 2
    assert log.count("c2") == 1
    assert log.count() == 3


def test_invalid_verdict_rejected(log: FeedbackLog) -> None:
    with pytest.raises(StructuredError):
        log.append(
            corpus_id="c1", item_type="np", pattern="X",
            verdict="banana",  # type: ignore[arg-type]
            decided_by="m",
        )


def test_empty_pattern_rejected(log: FeedbackLog) -> None:
    with pytest.raises(StructuredError) as excinfo:
        log.append(
            corpus_id="c1", item_type="np", pattern="   ",
            verdict="accept", decided_by="m",
        )
    assert excinfo.value.error_code == ErrorCode.VALIDATION_FAILED


def test_embedding_round_trip(log: FeedbackLog) -> None:
    vec = tuple(float(i) / 10 for i in range(384))
    entry = log.append(
        corpus_id="c1", item_type="np", pattern="X",
        verdict="accept", decided_by="m",
        pattern_embedding=vec,
    )
    embs = log.embeddings_for([entry.feedback_id])
    retrieved = embs[entry.feedback_id]
    assert retrieved is not None
    assert len(retrieved) == 384
    # Allow modest floating-point drift from float32 packing (38.x format)
    assert all(abs(a - b) < 1e-5 for a, b in zip(retrieved, vec, strict=True))
