"""Tests for `src.er.fuzzy_match.FuzzySchoolMatcher` + `CanonicalIndex` (FR-3 Pass 1)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.er.canonical_index import CanonicalIndex
from src.er.fuzzy_match import FuzzyMatch, FuzzySchoolMatcher


def _make_sqlite_with_aliases(path: Path, rows: list[tuple[str, str]]) -> Path:
    """rows = [(alias_text, canonical_id), ...]"""

    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE l1_school (
            canonical_id   TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL,
            city           TEXT,
            state          TEXT,
            country        TEXT,
            ada_code       TEXT,
            website        TEXT,
            source_dump_id TEXT NOT NULL,
            created_utc    TEXT NOT NULL
        );
        CREATE TABLE alias (
            alias_id       TEXT PRIMARY KEY,
            canonical_id   TEXT NOT NULL,
            alias_text     TEXT NOT NULL,
            alias_source   TEXT NOT NULL,
            confidence     REAL,
            created_utc    TEXT NOT NULL
        );
        """,
    )
    seen_canonicals: set[str] = set()
    for i, (alias, canonical_id) in enumerate(rows):
        if canonical_id not in seen_canonicals:
            conn.execute(
                "INSERT INTO l1_school (canonical_id, canonical_name, source_dump_id, created_utc) "
                "VALUES (?, ?, ?, ?)",
                (canonical_id, alias, "dump:test", "2026-05-21T00:00:00+00:00"),
            )
            seen_canonicals.add(canonical_id)
        conn.execute(
            "INSERT INTO alias (alias_id, canonical_id, alias_text, alias_source, "
            "confidence, created_utc) VALUES (?, ?, ?, ?, ?, ?)",
            (f"alias:{i}", canonical_id, alias, "manual", 1.0,
             "2026-05-21T00:00:00+00:00"),
        )
    conn.commit()
    conn.close()
    return path


def _index(tmp_path: Path, rows: list[tuple[str, str]]) -> CanonicalIndex:
    db = _make_sqlite_with_aliases(tmp_path / "side.db", rows)
    return CanonicalIndex(sqlite_path=db)


def test_canonical_index_loads_aliases_from_sqlite(tmp_path: Path) -> None:
    idx = _index(tmp_path, [
        ("New York University, College of Dentistry", "school:nyu"),
        ("Harvard School of Dental Medicine", "school:harvard"),
    ])

    assert idx.alias_count() == 2
    assert idx.canonical_count() == 2
    assert idx.canonical_name("school:nyu") == "New York University, College of Dentistry"


def test_canonical_index_returns_empty_when_db_missing(tmp_path: Path) -> None:
    idx = CanonicalIndex(sqlite_path=tmp_path / "missing.db")
    assert idx.alias_count() == 0
    assert idx.canonical_count() == 0
    assert idx.aliases() == {}


def test_canonical_index_groups_multiple_aliases_per_canonical(tmp_path: Path) -> None:
    idx = _index(tmp_path, [
        ("New York University, College of Dentistry", "school:nyu"),
        ("NYU College of Dentistry", "school:nyu"),
        ("NYU Dental", "school:nyu"),
    ])

    aliases = idx.aliases_for("school:nyu")
    assert set(aliases) == {
        "New York University, College of Dentistry",
        "NYU College of Dentistry",
        "NYU Dental",
    }


def test_matcher_exact_match_scores_100(tmp_path: Path) -> None:
    idx = _index(tmp_path, [("NYU College of Dentistry", "school:nyu")])
    matcher = FuzzySchoolMatcher(idx, threshold=80)

    result = matcher.match("NYU College of Dentistry")

    assert isinstance(result, FuzzyMatch)
    assert result.canonical_id == "school:nyu"
    assert result.score == pytest.approx(100.0)


def test_matcher_token_set_ratio_handles_reorder(tmp_path: Path) -> None:
    idx = _index(tmp_path, [("New York University College of Dentistry", "school:nyu")])
    matcher = FuzzySchoolMatcher(idx, threshold=90)

    result = matcher.match("College of Dentistry, New York University")

    assert result is not None
    assert result.canonical_id == "school:nyu"
    assert result.score >= 90


def test_matcher_returns_none_below_threshold(tmp_path: Path) -> None:
    idx = _index(tmp_path, [("Harvard School of Dental Medicine", "school:harvard")])
    matcher = FuzzySchoolMatcher(idx, threshold=95)

    assert matcher.match("Completely Unrelated University") is None


def test_matcher_returns_none_on_empty_input(tmp_path: Path) -> None:
    idx = _index(tmp_path, [("NYU", "school:nyu")])
    matcher = FuzzySchoolMatcher(idx)

    assert matcher.match("") is None
    assert matcher.match("   ") is None


def test_matcher_returns_none_with_empty_index(tmp_path: Path) -> None:
    idx = CanonicalIndex(sqlite_path=tmp_path / "missing.db")
    matcher = FuzzySchoolMatcher(idx)

    assert matcher.match("anything") is None


def test_matcher_picks_best_above_threshold(tmp_path: Path) -> None:
    idx = _index(tmp_path, [
        ("Harvard School of Dental Medicine", "school:harvard"),
        ("Harvard Medical School", "school:harvard_med"),
        ("Yale School of Medicine", "school:yale"),
    ])
    matcher = FuzzySchoolMatcher(idx, threshold=70)

    result = matcher.match("Harvard School of Dental Med")

    assert result is not None
    assert result.canonical_id == "school:harvard"


def test_matcher_match_many_returns_per_mention_result(tmp_path: Path) -> None:
    idx = _index(tmp_path, [
        ("NYU College of Dentistry", "school:nyu"),
        ("Harvard School of Dental Medicine", "school:harvard"),
    ])
    matcher = FuzzySchoolMatcher(idx, threshold=80)

    results = matcher.match_many(
        ["NYU College of Dentistry", "garbage text here", "Harvard School of Dental Medicine"],
    )

    assert len(results) == 3
    assert results[0] is not None
    assert results[0].canonical_id == "school:nyu"
    assert results[1] is None
    assert results[2] is not None
    assert results[2].canonical_id == "school:harvard"


def test_matcher_threshold_validation(tmp_path: Path) -> None:
    idx = _index(tmp_path, [("X", "school:x")])

    with pytest.raises(ValueError):
        FuzzySchoolMatcher(idx, threshold=-1)
    with pytest.raises(ValueError):
        FuzzySchoolMatcher(idx, threshold=150)


def test_matcher_is_case_insensitive(tmp_path: Path) -> None:
    idx = _index(tmp_path, [("Harvard School of Dental Medicine", "school:harvard")])
    matcher = FuzzySchoolMatcher(idx, threshold=95)

    upper = matcher.match("HARVARD SCHOOL OF DENTAL MEDICINE")
    mixed = matcher.match("haRVard SchOOL of dental medicine")

    assert upper is not None
    assert mixed is not None
    assert upper.canonical_id == "school:harvard"
    assert mixed.canonical_id == "school:harvard"


def test_matcher_returns_canonical_name_not_matched_alias(tmp_path: Path) -> None:
    idx = _index(tmp_path, [
        ("New York University, College of Dentistry", "school:nyu"),
        ("NYU College of Dentistry", "school:nyu"),
    ])
    matcher = FuzzySchoolMatcher(idx, threshold=95)

    result = matcher.match("NYU College of Dentistry")

    assert result is not None
    assert result.canonical_id == "school:nyu"
    # canonical_name comes from l1_school table, which uses the first alias inserted
    assert result.canonical_name == "New York University, College of Dentistry"
    # matched_alias preserves which alias scored
    assert result.matched_alias == "NYU College of Dentistry"
