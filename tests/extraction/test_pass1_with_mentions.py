"""Tests for the MENTIONS_SCHOOL emission path in `Pass1StructuralBuilder`."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.er.canonical_index import CanonicalIndex
from src.extraction.pass1_mention_extractor import Pass1MentionExtractor
from src.extraction.pass1_structural import Pass1StructuralBuilder
from src.ingestion.adapters.l5_reddit import (
    L5RedditResult,
    RedditComment,
    RedditPost,
    RedditUser,
)
from src.ingestion.adapters.l5_sdn import L5SDNResult, SDNPost, SDNThread


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
            (f"alias:{cid}", cid, name, "manual", 1.0, "2026-05-21T00:00:00+00:00"),
        )
    conn.commit()
    conn.close()
    return CanonicalIndex(sqlite_path=db_path)


def _utc(year: int, month: int = 1, day: int = 1) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


def _reddit_post(
    pid: str, title: str, body: str = "",
    author: str | None = "reddit:DentalSchool:alice",
) -> RedditPost:
    return RedditPost(
        post_id=f"reddit_post:{pid}", raw_id=pid, subreddit="DentalSchool",
        author_user_id=author, raw_author="alice" if author else None,
        title=title, selftext=body, created_utc=_utc(2020, 1, 1),
        score=10, ups=10, downs=0, num_comments=0,
        link_flair_text=None, permalink=None, url=None, over_18=False,
    )


def test_post_with_school_mention_emits_mentions_school_edge(tmp_path: Path) -> None:
    idx = _seed_index(tmp_path / "x.db")
    ex = Pass1MentionExtractor(idx)
    result = L5RedditResult(
        subreddit="DentalSchool",
        posts=[_reddit_post(
            "abc",
            title="Accepted to Harvard School of Dental Medicine!",
            body="So excited.",
        )],
        comments=[], users=[],
    )

    out = Pass1StructuralBuilder().assemble_reddit(
        result, ingest_time=_utc(2026, 5, 21), mention_extractor=ex,
    )

    mention_edges = [e for e in out.edges if e.label == "MENTIONS_SCHOOL"]
    assert len(mention_edges) == 1
    e = mention_edges[0]
    assert e.from_id == "reddit_post:abc"
    assert e.to_id == "school:harvard"
    assert e.source_tier == "L5"
    assert e.rank == "normal"
    assert e.references == ["reddit_post:abc"]
    assert 0.9 <= e.confidence <= 1.0
    assert e.qualifiers["needs_review"] is False


def test_post_without_mention_emits_no_mentions_edge(tmp_path: Path) -> None:
    idx = _seed_index(tmp_path / "x.db")
    ex = Pass1MentionExtractor(idx)
    result = L5RedditResult(
        subreddit="DentalSchool",
        posts=[_reddit_post("abc", title="Hello world", body="random body")],
        comments=[], users=[],
    )

    out = Pass1StructuralBuilder().assemble_reddit(
        result, ingest_time=_utc(2026, 5, 21), mention_extractor=ex,
    )

    assert [e for e in out.edges if e.label == "MENTIONS_SCHOOL"] == []


def test_omitting_extractor_skips_mention_path(tmp_path: Path) -> None:
    """Backwards compat: caller without an extractor gets only structural edges."""

    result = L5RedditResult(
        subreddit="DentalSchool",
        posts=[_reddit_post("abc", title="Harvard School of Dental Medicine accepted me")],
        comments=[], users=[],
    )

    out = Pass1StructuralBuilder().assemble_reddit(
        result, ingest_time=_utc(2026, 5, 21),
    )

    assert [e for e in out.edges if e.label == "MENTIONS_SCHOOL"] == []


def test_mentions_school_emitted_for_comment_too(tmp_path: Path) -> None:
    idx = _seed_index(tmp_path / "x.db")
    ex = Pass1MentionExtractor(idx)
    result = L5RedditResult(
        subreddit="DentalSchool",
        posts=[_reddit_post("abc", title="advice on dental schools?")],
        comments=[RedditComment(
            comment_id="reddit_comment:c1", raw_id="c1", subreddit="DentalSchool",
            post_id="reddit_post:abc", parent_id="reddit_post:abc",
            author_user_id="reddit:DentalSchool:bob", raw_author="bob",
            body="I'd recommend Harvard School of Dental Medicine for sure.",
            created_utc=_utc(2020, 1, 2), score=5, ups=5, downs=0,
            controversiality=0,
        )],
        users=[RedditUser(
            user_id="reddit:DentalSchool:bob", username="bob",
            subreddit="DentalSchool", first_seen_utc=_utc(2020, 1, 2),
        )],
    )

    out = Pass1StructuralBuilder().assemble_reddit(
        result, ingest_time=_utc(2026, 5, 21), mention_extractor=ex,
    )

    mention_edges = [e for e in out.edges if e.label == "MENTIONS_SCHOOL"]
    from_ids = {e.from_id for e in mention_edges}
    assert "reddit_comment:c1" in from_ids


def test_borderline_score_marks_needs_review_in_qualifiers(tmp_path: Path) -> None:
    idx = _seed_index(tmp_path / "x.db")
    ex = Pass1MentionExtractor(
        idx, auto_accept_threshold=98, hitl_lower_threshold=75,
    )
    result = L5RedditResult(
        subreddit="DentalSchool",
        posts=[_reddit_post("abc", title="Harvard School of Dental Medicine accepted me")],
        comments=[], users=[],
    )
    out = Pass1StructuralBuilder().assemble_reddit(
        result, ingest_time=_utc(2026, 5, 21), mention_extractor=ex,
    )
    mention_edges = [e for e in out.edges if e.label == "MENTIONS_SCHOOL"]
    # Score will be ~100 on exact match → still no review needed
    assert all(isinstance(e.qualifiers["needs_review"], bool) for e in mention_edges)


def test_sdn_post_mentions_emit_edges(tmp_path: Path) -> None:
    idx = _seed_index(tmp_path / "x.db")
    ex = Pass1MentionExtractor(idx)
    thread = SDNThread(
        thread_id="sdn_thread:1", raw_thread_id="1",
        title="Harvard School of Dental Medicine acceptance thread",
        category="Pre-Dental", url="u", reply_count=None, view_count=None,
        root_post_id="sdn_post:1:a",
    )
    post = SDNPost(
        post_id="sdn_post:1:a", raw_post_id="a", thread_id="sdn_thread:1",
        thread_url="u", thread_title="Harvard School of Dental Medicine acceptance thread",
        category="Pre-Dental", page_number=1,
        author_user_id="sdn:alice", raw_author="alice",
        body="Got my Harvard School of Dental Medicine acceptance letter today!",
        created_utc=_utc(2020, 1, 1), is_thread_root=True,
    )
    sdn = L5SDNResult(posts=[post], users=[], threads=[thread])

    out = Pass1StructuralBuilder().assemble_sdn(
        sdn, ingest_time=_utc(2026, 5, 21), mention_extractor=ex,
    )

    mention_edges = [e for e in out.edges if e.label == "MENTIONS_SCHOOL"]
    assert len(mention_edges) == 1
    assert mention_edges[0].from_id == "sdn_post:1:a"
    assert mention_edges[0].to_id == "school:harvard"


def test_mention_edge_carries_alias_and_score_in_qualifiers(tmp_path: Path) -> None:
    idx = _seed_index(tmp_path / "x.db")
    ex = Pass1MentionExtractor(idx)
    result = L5RedditResult(
        subreddit="DentalSchool",
        posts=[_reddit_post("abc", title="Harvard School of Dental Medicine acceptance!")],
        comments=[], users=[],
    )
    out = Pass1StructuralBuilder().assemble_reddit(
        result, ingest_time=_utc(2026, 5, 21), mention_extractor=ex,
    )
    e = next(x for x in out.edges if x.label == "MENTIONS_SCHOOL")
    assert "matched_alias" in e.qualifiers
    assert "score" in e.qualifiers
    assert e.qualifiers["score"] == pytest.approx(e.confidence * 100.0, abs=0.1)


def test_mention_edges_only_appear_once_per_post_per_school(tmp_path: Path) -> None:
    """If a post repeats the same school name in title and body, only one edge."""

    idx = _seed_index(tmp_path / "x.db")
    ex = Pass1MentionExtractor(idx)
    result = L5RedditResult(
        subreddit="DentalSchool",
        posts=[_reddit_post(
            "abc",
            title="Harvard School of Dental Medicine acceptance",
            body="Just got my Harvard School of Dental Medicine letter!",
        )],
        comments=[], users=[],
    )
    out = Pass1StructuralBuilder().assemble_reddit(
        result, ingest_time=_utc(2026, 5, 21), mention_extractor=ex,
    )

    edges = [e for e in out.edges if e.label == "MENTIONS_SCHOOL"]
    assert len(edges) == 1
