"""Precision guards for Pass-1 mention matching (the r/predental flood fixes)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.er.canonical_index import CanonicalIndex
from src.extraction.pass1_mention_extractor import Pass1MentionExtractor


def _index(tmp_path: Path) -> CanonicalIndex:
    db = tmp_path / "store.db"
    if db.exists():                       # reentrant: reuse within a test
        return CanonicalIndex(sqlite_path=db)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE alias (alias_text TEXT, canonical_id TEXT)")
    conn.execute(
        "CREATE TABLE l1_school (canonical_id TEXT, canonical_name TEXT, city TEXT, "
        "state TEXT, country TEXT, source_dump_id TEXT, created_utc TEXT)",
    )
    conn.executemany("INSERT INTO alias VALUES (?,?)", [
        ("CU Dental", "school:colorado"),
        ("University of Colorado School of Dental Medicine", "school:colorado"),
        ("Case", "school:case_western"),
        ("Case Western Reserve University School of Dental Medicine", "school:case_western"),
        ("Penn", "school:upenn"),
        ("University of Pennsylvania", "school:upenn"),  # tail-stripped alias (real)
        ("University of Pennsylvania School of Dental Medicine", "school:upenn"),
        ("V.A. Northern California Health Care System Mare Island", "institution:va_norcal"),
    ])
    conn.executemany(
        "INSERT INTO l1_school (canonical_id, canonical_name, state) VALUES (?,?,?)", [
            ("school:colorado", "University of Colorado School of Dental Medicine", "CO"),
            ("school:case_western", "Case Western Reserve University School of Dental Medicine", "OH"),
            ("school:upenn", "University of Pennsylvania School of Dental Medicine", "PA"),
            ("institution:va_norcal", "V.A. Northern California Health Care System Mare Island", "CA"),
        ],
    )
    conn.commit()
    conn.close()
    return CanonicalIndex(sqlite_path=db)


def _hits(tmp_path: Path, text: str) -> set[str]:
    ex = Pass1MentionExtractor(_index(tmp_path))
    return {m.canonical_id for m in ex.extract(text)}


def test_cu_dental_does_not_flood_generic_dental_posts(tmp_path: Path) -> None:
    # "CU Dental" must NOT match a post merely containing the word "dental".
    assert "school:colorado" not in _hits(
        tmp_path, "starting my dental school journey, studying for the dat",
    )


def test_real_colorado_mention_still_matches(tmp_path: Path) -> None:
    assert "school:colorado" in _hits(
        tmp_path, "I just got into the University of Colorado School of Dental Medicine!",
    )


def test_short_alias_case_sensitive_no_common_word(tmp_path: Path) -> None:
    # "Case" (the school) must not fire on the lowercase word "case".
    assert "school:case_western" not in _hits(tmp_path, "just in case it does not work out")
    # but a capitalized real mention matches.
    assert "school:case_western" in _hits(tmp_path, "I interviewed at Case Western last week")


def test_long_institution_not_matched_on_one_common_token(tmp_path: Path) -> None:
    # A long institution name must not match on a single common token.
    assert "institution:va_norcal" not in _hits(
        tmp_path, "the california health care system is hard to navigate",
    )


def test_misspelling_recall_preserved(tmp_path: Path) -> None:
    # The distinctive long token still matches misspellings (fuzzy recall).
    assert "school:upenn" in _hits(
        tmp_path, "applying to university of pennsylvana this cycle",
    )
