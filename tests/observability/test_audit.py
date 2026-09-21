"""Tests for `src.observability.audit.AuditLog` (FR-11)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.observability import AuditLog, AuditRow


def _log(tmp_path: Path) -> AuditLog:
    return AuditLog(sqlite_path=tmp_path / "audit.db")


def test_log_extraction_enforces_ttl_3600(tmp_path: Path) -> None:
    a = _log(tmp_path)

    aid = a.log_extraction(
        thread_content_hash="abc", prompt_template_id="sentiment.v1",
        prompt_version="1.0", schema_hash="s", model="haiku-4.5",
        model_version="2026", cache_hit=False, cache_key="cache:abc",
        ttl_pinned=3600, input_tokens=100, output_tokens=20,
        cached_input_tokens=0, cost_usd=0.001, latency_ms=200,
    )

    assert aid.startswith("audit:")
    assert a.count() == 1


def test_log_extraction_rejects_non_3600_ttl(tmp_path: Path) -> None:
    a = _log(tmp_path)
    with pytest.raises(ValueError, match="ttl_pinned=3600"):
        a.log_extraction(ttl_pinned=600)


def test_log_retrieval_allows_no_ttl(tmp_path: Path) -> None:
    a = _log(tmp_path)
    aid = a.log_retrieval(
        query_text="nyu", result_count=5, latency_ms=80,
        traversal_depth=3, time_range=None, as_of=None,
    )
    assert aid.startswith("audit:")


def test_log_hitl_records_decision(tmp_path: Path) -> None:
    a = _log(tmp_path)
    aid = a.log_hitl(
        reviewer="mahyar", decision="accept", item_type="alias_match",
        before={"alias": "UPenn"}, after={"canonical_id": "school:upenn"},
    )
    assert aid.startswith("audit:")
    assert a.count(kind="hitl") == 1


def test_query_filters_by_kind_and_since(tmp_path: Path) -> None:
    a = _log(tmp_path)
    a.log_extraction(ttl_pinned=3600, model="haiku", cache_hit=False)
    a.log_retrieval(query_text="x", result_count=1)
    a.log_hitl(reviewer="r", decision="accept")

    assert a.count() == 3
    assert a.count(kind="extraction") == 1
    assert a.count(kind="retrieval") == 1

    extractions = a.query(kind="extraction")
    assert len(extractions) == 1
    assert isinstance(extractions[0], AuditRow)
    assert extractions[0].ttl_pinned == 3600


def test_query_orders_by_ts_desc(tmp_path: Path) -> None:
    a = _log(tmp_path)
    base = datetime(2026, 5, 21, tzinfo=UTC)
    a.log_retrieval(query_text="q1", ts=base)
    a.log_retrieval(query_text="q2", ts=base + timedelta(minutes=1))
    a.log_retrieval(query_text="q3", ts=base + timedelta(minutes=2))

    rows = a.query()
    assert rows[0].fields["query_text"] == "q3"
    assert rows[-1].fields["query_text"] == "q1"


def test_audit_row_carries_full_field_payload(tmp_path: Path) -> None:
    a = _log(tmp_path)
    a.log_ingestion(dump_id="dump:abc", source_tier="L1", file_count=5)

    rows = a.query(kind="ingestion")
    assert rows[0].fields["dump_id"] == "dump:abc"
    assert rows[0].fields["source_tier"] == "L1"
    assert rows[0].fields["file_count"] == 5
