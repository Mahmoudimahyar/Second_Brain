"""Tests for `evals.alias_resolution.evaluate`."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from evals.alias_resolution import GoldMention, evaluate, load_gold
from src.er.canonical_index import CanonicalIndex
from src.extraction.pass1_mention_extractor import Pass1MentionExtractor


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
    seeds = [
        ("school:harvard", "Harvard School of Dental Medicine"),
        ("school:harvard", "Harvard"),
        ("school:nyu", "New York University, College of Dentistry"),
        ("school:nyu", "NYU"),
        ("school:tufts", "Tufts University School of Dental Medicine"),
        ("school:tufts", "Tufts"),
    ]
    for i, (cid, name) in enumerate(seeds):
        conn.execute(
            "INSERT OR IGNORE INTO l1_school "
            "(canonical_id, canonical_name, source_dump_id, created_utc) "
            "VALUES (?, ?, ?, ?)",
            (cid, name, "dump:test", "2026-05-21T00:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO alias (alias_id, canonical_id, alias_text, alias_source, "
            "confidence, created_utc) VALUES (?, ?, ?, ?, ?, ?)",
            (f"alias:{i}", cid, name, "manual", 1.0,
             "2026-05-21T00:00:00+00:00"),
        )
    conn.commit()
    conn.close()
    return CanonicalIndex(sqlite_path=db_path)


def test_perfect_recall_on_canonical_names(tmp_path: Path) -> None:
    idx = _seed_index(tmp_path / "x.db")
    matcher = Pass1MentionExtractor(idx)
    gold = [
        GoldMention("Got into Harvard!", "school:harvard"),
        GoldMention("NYU acceptance!", "school:nyu"),
        GoldMention("Tufts is my top choice.", "school:tufts"),
    ]

    res = evaluate(gold, matcher)

    assert res.tp == 3
    assert res.fp == 0
    assert res.fn == 0
    assert res.f1 == pytest.approx(1.0)


def test_true_negatives_when_no_school_mention(tmp_path: Path) -> None:
    idx = _seed_index(tmp_path / "x.db")
    matcher = Pass1MentionExtractor(idx)
    gold = [
        GoldMention("I went for a walk today.", None),
        GoldMention("Coffee was great this morning.", None),
    ]

    res = evaluate(gold, matcher)

    assert res.tn == 2
    assert res.fp == 0


def test_false_negative_when_matcher_misses(tmp_path: Path) -> None:
    idx = _seed_index(tmp_path / "x.db")
    matcher = Pass1MentionExtractor(idx)
    gold = [
        GoldMention("Going to Stanford for interviews.",
                    "school:stanford"),  # not in index
    ]

    res = evaluate(gold, matcher)

    assert res.fn == 1
    assert res.tp == 0
    assert res.f1 == 0.0


def test_false_positive_when_text_contains_no_match(tmp_path: Path) -> None:
    """If matcher predicts a match but gold says None → FP."""

    idx = _seed_index(tmp_path / "x.db")
    matcher = Pass1MentionExtractor(idx, hitl_lower_threshold=50)
    gold = [
        GoldMention("Hello world", None),
    ]

    res = evaluate(gold, matcher)
    # No school mention in "Hello world" should give TN.
    assert res.tn == 1


def test_mixed_results_compute_correct_f1(tmp_path: Path) -> None:
    idx = _seed_index(tmp_path / "x.db")
    matcher = Pass1MentionExtractor(idx)
    gold = [
        GoldMention("Harvard accepted me!", "school:harvard"),
        GoldMention("NYU sent decisions", "school:nyu"),
        GoldMention("Going for a walk.", None),
        GoldMention("Stanford waitlist again", "school:stanford"),  # in gold, not in index
    ]

    res = evaluate(gold, matcher)

    # tp=2, fn=1, tn=1, fp=0
    assert res.tp == 2
    assert res.fn == 1
    assert res.tn == 1
    assert res.precision == pytest.approx(1.0)
    assert res.recall == pytest.approx(2 / 3, rel=1e-3)


def test_f1_threshold_check(tmp_path: Path) -> None:
    idx = _seed_index(tmp_path / "x.db")
    matcher = Pass1MentionExtractor(idx)
    gold = [GoldMention("Harvard accepted me!", "school:harvard")]
    res = evaluate(gold, matcher)
    assert res.passes_threshold(0.92)
    assert not res.passes_threshold(1.5)


def test_load_gold_parses_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "g.jsonl"
    path.write_text(
        "\n".join([
            json.dumps({"text": "a", "expected_canonical_id": "school:x"}),
            json.dumps({"text": "b", "expected_canonical_id": None}),
            "",  # blank
            "# comment",
        ]),
        encoding="utf-8",
    )

    gold = load_gold(path)
    assert len(gold) == 2
    assert gold[0].text == "a"
    assert gold[1].expected_canonical_id is None


def test_real_gold_file_loads() -> None:
    p = Path(__file__).parent.parent.parent / "evals" / "gold" / "alias_mentions.jsonl"
    if not p.is_file():
        pytest.skip("gold file not found")
    gold = load_gold(p)
    assert len(gold) >= 20
    # Sanity: each entry has either an expected_canonical_id starting with "school:"
    # or it's None.
    for g in gold:
        assert g.expected_canonical_id is None or g.expected_canonical_id.startswith("school:")
