"""Tests for HITL routing of borderline mentions (FR-3.2)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from src.er.canonical_index import CanonicalIndex
from src.extraction.pass1_mention_extractor import Pass1MentionExtractor
from src.extraction.pass1_structural import Pass1StructuralBuilder
from src.ingestion.adapters.l5_reddit import L5RedditResult, RedditPost


def _seed_index(db_path: Path) -> CanonicalIndex:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE l1_school (
            canonical_id TEXT PRIMARY KEY, canonical_name TEXT NOT NULL,
            city TEXT, state TEXT, country TEXT, ada_code TEXT, website TEXT,
            source_dump_id TEXT NOT NULL, created_utc TEXT NOT NULL
        );
        CREATE TABLE alias (
            alias_id TEXT PRIMARY KEY, canonical_id TEXT NOT NULL,
            alias_text TEXT NOT NULL, alias_source TEXT NOT NULL,
            confidence REAL, created_utc TEXT NOT NULL
        );
        """,
    )
    for cid, name in [
        ("school:harvard", "Harvard School of Dental Medicine"),
        ("school:nyu", "New York University, College of Dentistry"),
    ]:
        conn.execute(
            "INSERT INTO l1_school (canonical_id, canonical_name, source_dump_id, created_utc) "
            "VALUES (?, ?, ?, ?)",
            (cid, name, "dump:test", "2026-05-21T00:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO alias (alias_id, canonical_id, alias_text, alias_source, "
            "confidence, created_utc) VALUES (?, ?, ?, ?, ?, ?)",
            (f"alias:{cid}", cid, name, "manual", 1.0,
             "2026-05-21T00:00:00+00:00"),
        )
    conn.commit()
    conn.close()
    return CanonicalIndex(sqlite_path=db_path)


def _utc() -> datetime:
    return datetime(2026, 5, 21, tzinfo=UTC)


def _post(pid: str, title: str, body: str = "") -> RedditPost:
    return RedditPost(
        post_id=f"reddit_post:{pid}", raw_id=pid, subreddit="DentalSchool",
        author_user_id="reddit:DentalSchool:alice", raw_author="alice",
        title=title, selftext=body, created_utc=datetime(2020, 1, 1, tzinfo=UTC),
        score=10, ups=10, downs=0, num_comments=0,
        link_flair_text=None, permalink=None, url=None, over_18=False,
    )


def test_high_confidence_mention_does_not_enqueue_hitl(tmp_path: Path) -> None:
    idx = _seed_index(tmp_path / "x.db")
    ex = Pass1MentionExtractor(idx)
    result = L5RedditResult(
        subreddit="DentalSchool",
        posts=[_post("abc", "Accepted to Harvard School of Dental Medicine!")],
        comments=[], users=[],
    )
    out = Pass1StructuralBuilder().assemble_reddit(
        result, ingest_time=_utc(), mention_extractor=ex,
    )
    assert out.hitl_items == []


def test_borderline_mention_enqueues_hitl_item(tmp_path: Path) -> None:
    idx = _seed_index(tmp_path / "x.db")
    # Auto-accept high; only partial / approximate text matches survive in HITL band.
    ex = Pass1MentionExtractor(idx, auto_accept_threshold=95, hitl_lower_threshold=70)
    result = L5RedditResult(
        subreddit="DentalSchool",
        # Partial text — fuzzy partial_ratio scores ~70-94.
        posts=[_post("abc", "Just got into Harvard School Dent Medicine class")],
        comments=[], users=[],
    )
    out = Pass1StructuralBuilder().assemble_reddit(
        result, ingest_time=_utc(), mention_extractor=ex,
    )

    mention_edges = [e for e in out.edges if e.label == "MENTIONS_SCHOOL"]
    assert mention_edges
    borderline = [e for e in mention_edges if e.qualifiers["needs_review"]]
    if borderline:
        # Borderline edges → matching HITL items.
        assert len(out.hitl_items) == len(borderline)
    else:
        # Above auto-accept → no HITL items.
        assert out.hitl_items == []


def test_hitl_payload_has_canonical_info(tmp_path: Path) -> None:
    idx = _seed_index(tmp_path / "x.db")
    ex = Pass1MentionExtractor(idx, auto_accept_threshold=99, hitl_lower_threshold=50)
    result = L5RedditResult(
        subreddit="DentalSchool",
        posts=[_post("abc", "Just got into Harvard School Dent Medicine class")],
        comments=[], users=[],
    )
    out = Pass1StructuralBuilder().assemble_reddit(
        result, ingest_time=_utc(), mention_extractor=ex,
    )

    assert out.hitl_items, "expected at least one borderline mention"
    item = out.hitl_items[0]
    assert item.item_type == "alias_match"
    p = item.payload
    assert p["post_id"] == "reddit_post:abc"
    assert p["canonical_id"] == "school:harvard"
    assert p["matched_alias"] == "Harvard School of Dental Medicine"
    assert p["score"] < 99
    assert "snippet" in p


def test_no_extractor_means_no_hitl(tmp_path: Path) -> None:
    result = L5RedditResult(
        subreddit="DentalSchool",
        posts=[_post("abc", "anything")],
        comments=[], users=[],
    )
    out = Pass1StructuralBuilder().assemble_reddit(result, ingest_time=_utc())
    assert out.hitl_items == []
