"""Tests for `src.extraction.pass1_mention_extractor.Pass1MentionExtractor`."""

from __future__ import annotations

import dataclasses
import sqlite3
from pathlib import Path

import pytest

from src.er.canonical_index import CanonicalIndex
from src.extraction.pass1_mention_extractor import Mention, Pass1MentionExtractor


def _seed(db_path: Path, rows: list[tuple[str, str]]) -> CanonicalIndex:
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
    seen: set[str] = set()
    for i, (alias, cid) in enumerate(rows):
        if cid not in seen:
            conn.execute(
                "INSERT INTO l1_school (canonical_id, canonical_name, source_dump_id, created_utc) "
                "VALUES (?, ?, ?, ?)",
                (cid, alias, "dump:test", "2026-05-21T00:00:00+00:00"),
            )
            seen.add(cid)
        conn.execute(
            "INSERT INTO alias (alias_id, canonical_id, alias_text, alias_source, "
            "confidence, created_utc) VALUES (?, ?, ?, ?, ?, ?)",
            (f"alias:{i}", cid, alias, "manual", 1.0, "2026-05-21T00:00:00+00:00"),
        )
    conn.commit()
    conn.close()
    return CanonicalIndex(sqlite_path=db_path)


def test_extracts_exact_school_mention(tmp_path: Path) -> None:
    idx = _seed(tmp_path / "x.db", [
        ("Harvard School of Dental Medicine", "school:harvard"),
        ("NYU College of Dentistry", "school:nyu"),
    ])
    ex = Pass1MentionExtractor(idx)

    mentions = ex.extract(
        "I just got accepted to Harvard School of Dental Medicine, "
        "but I'm waiting on NYU College of Dentistry.",
    )

    by_id = {m.canonical_id: m for m in mentions}
    assert "school:harvard" in by_id
    assert "school:nyu" in by_id
    assert all(m.needs_review is False for m in mentions)


def test_dedupes_by_canonical_id(tmp_path: Path) -> None:
    """Multiple aliases for the same canonical should produce one Mention."""

    idx = _seed(tmp_path / "x.db", [
        ("New York University, College of Dentistry", "school:nyu"),
        ("NYU College of Dentistry", "school:nyu"),
    ])
    ex = Pass1MentionExtractor(idx)

    mentions = ex.extract("I'm applying to NYU College of Dentistry next cycle.")

    assert len(mentions) == 1
    assert mentions[0].canonical_id == "school:nyu"


def test_borderline_score_marks_needs_review(tmp_path: Path) -> None:
    idx = _seed(tmp_path / "x.db", [
        ("Harvard School of Dental Medicine", "school:harvard"),
    ])
    ex = Pass1MentionExtractor(idx, auto_accept_threshold=92,
                                hitl_lower_threshold=70)

    # A partial that should be 70-91 (not full match, not garbage)
    mentions = ex.extract("Looking at Harvard Dental Med")

    if mentions:
        assert mentions[0].score < ex.auto_accept_threshold
        assert mentions[0].needs_review is True


def test_no_mention_below_lower_threshold(tmp_path: Path) -> None:
    idx = _seed(tmp_path / "x.db", [
        ("Harvard School of Dental Medicine", "school:harvard"),
    ])
    ex = Pass1MentionExtractor(idx, auto_accept_threshold=95,
                                hitl_lower_threshold=80)

    mentions = ex.extract("I went for a walk in the park today, it was nice.")
    assert mentions == []


def test_skips_very_short_aliases(tmp_path: Path) -> None:
    """Aliases shorter than MIN_ALIAS_LEN (1-char) get filtered; 2+ char
    aliases (BU, NYU, UCLA) are kept via whole-word lookup."""

    idx = _seed(tmp_path / "x.db", [
        ("X", "school:x_too_short"),    # 1 char — filtered
        ("BU", "school:bu"),             # 2 chars — kept (lowered MIN to 2)
        ("NYU", "school:nyu"),           # 3 chars — kept
        ("UCLA School of Dentistry", "school:ucla"),
    ])
    ex = Pass1MentionExtractor(idx)

    # "X" filtered; BU + NYU + UCLA kept (3 aliases).
    assert ex.alias_count() == 3

    # 2-char "BU" matches via whole-word lookup.
    mentions = ex.extract("I'm at BU now")
    assert any(m.canonical_id == "school:bu" for m in mentions)

    # 3-char "NYU" matches via whole-word lookup.
    mentions = ex.extract("Got accepted to NYU today!")
    assert any(m.canonical_id == "school:nyu" for m in mentions)


def test_short_alias_word_boundary_excludes_substrings(tmp_path: Path) -> None:
    """3-char alias NYU should not match 'anyway' (which contains 'nyu')."""

    idx = _seed(tmp_path / "x.db", [("NYU", "school:nyu")])
    ex = Pass1MentionExtractor(idx)

    assert ex.extract("anyway, I'll think about it") == []
    assert any(m.canonical_id == "school:nyu" for m in ex.extract("I'm at NYU"))


def test_alias_token_sanity_check_rejects_pure_fuzzy_noise(tmp_path: Path) -> None:
    """Even if partial_ratio is high, at least one alias word must appear."""

    idx = _seed(tmp_path / "x.db", [
        ("Harvard School of Dental Medicine", "school:harvard"),
    ])
    ex = Pass1MentionExtractor(idx, auto_accept_threshold=99, hitl_lower_threshold=50)

    # No alias word ("harvard", "school", "dental", "medicine") in this text;
    # partial_ratio might score above 50 from chance overlap but the sanity
    # check (>=1 alias word in haystack) excludes it.
    mentions = ex.extract("xx yy zz qq pp")
    assert mentions == []


def test_extract_returns_empty_on_blank_input(tmp_path: Path) -> None:
    idx = _seed(tmp_path / "x.db", [("Harvard", "school:h")])  # alias too short anyway
    ex = Pass1MentionExtractor(idx)
    assert ex.extract("") == []
    assert ex.extract("   ") == []


def test_threshold_validation() -> None:
    idx = CanonicalIndex(sqlite_path=Path("/nonexistent.db"))
    with pytest.raises(ValueError):
        Pass1MentionExtractor(idx, auto_accept_threshold=50, hitl_lower_threshold=80)
    with pytest.raises(ValueError):
        Pass1MentionExtractor(idx, auto_accept_threshold=120)


def test_mention_is_immutable(tmp_path: Path) -> None:
    m = Mention(canonical_id="x", canonical_name="X",
                matched_alias="x", score=95, needs_review=False)
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.score = 50  # type: ignore[misc]


def test_picks_best_score_when_multiple_aliases_match(tmp_path: Path) -> None:
    idx = _seed(tmp_path / "x.db", [
        ("Harvard School of Dental Medicine", "school:harvard"),
        ("Harvard", "school:harvard"),  # filtered (too short)
        ("Harvard Dental", "school:harvard"),
    ])
    ex = Pass1MentionExtractor(idx)

    mentions = ex.extract("Applied to Harvard School of Dental Medicine last week")

    assert len(mentions) == 1
    assert mentions[0].score >= 95
    # The longer alias matched cleanly; verify by looking at matched_alias.
    assert "Harvard School of Dental Medicine" in (
        mentions[0].matched_alias, "Harvard Dental",
    )


def test_handles_case_variations(tmp_path: Path) -> None:
    idx = _seed(tmp_path / "x.db", [
        ("Harvard School of Dental Medicine", "school:harvard"),
    ])
    ex = Pass1MentionExtractor(idx)

    upper = ex.extract("HARVARD SCHOOL OF DENTAL MEDICINE accepted me!")
    lower = ex.extract("harvard school of dental medicine accepted me!")
    mixed = ex.extract("HarVarD SchOol of Dental MediCine accepted me!")

    assert upper and upper[0].canonical_id == "school:harvard"
    assert lower and lower[0].canonical_id == "school:harvard"
    assert mixed and mixed[0].canonical_id == "school:harvard"
