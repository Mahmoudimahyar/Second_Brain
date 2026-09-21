"""Tests for the NER-first mention extractor (ADR-022) — injected fake model."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.er.canonical_index import CanonicalIndex
from src.extraction.ner_mention_extractor import NERMentionExtractor


class _FakeNER:
    """Stand-in for GLiNER/NuNER: returns pre-canned spans (no model load)."""

    def __init__(self, spans: list[dict[str, object]]) -> None:
        self._spans = spans

    def predict_entities(
        self, text: str, labels: list[str], threshold: float,
    ) -> list[dict[str, object]]:
        return self._spans


def _index(tmp_path: Path) -> CanonicalIndex:
    db = tmp_path / "store.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE alias (alias_text TEXT, canonical_id TEXT)")
    conn.execute("CREATE TABLE l1_school (canonical_id TEXT, canonical_name TEXT)")
    conn.executemany("INSERT INTO alias VALUES (?,?)", [
        ("University of Pennsylvania School of Dental Medicine", "school:upenn"),
        ("UPenn", "school:upenn"),
        ("Oral and Maxillofacial Surgery", "specialty:omfs"),
    ])
    conn.executemany("INSERT INTO l1_school VALUES (?,?)", [
        ("school:upenn", "University of Pennsylvania School of Dental Medicine"),
        ("specialty:omfs", "Oral and Maxillofacial Surgery"),
    ])
    conn.commit()
    conn.close()
    return CanonicalIndex(sqlite_path=db)


def test_resolves_ner_spans_to_canonical(tmp_path: Path) -> None:
    idx = _index(tmp_path)
    fake = _FakeNER([
        {"text": "University of Pennsylvania", "label": "university", "score": 0.9},
        {"text": "Oral and Maxillofacial Surgery", "label": "dental specialty",
         "score": 0.95},
    ])
    ex = NERMentionExtractor(idx, model=fake)
    mentions = {m.canonical_id for m in ex.extract("… some forum post …")}
    assert mentions == {"school:upenn", "specialty:omfs"}


def test_unresolvable_span_dropped(tmp_path: Path) -> None:
    idx = _index(tmp_path)
    fake = _FakeNER([{"text": "Hogwarts", "label": "university", "score": 0.9}])
    ex = NERMentionExtractor(idx, model=fake)
    assert ex.extract("…") == []


def test_dedupes_by_canonical_keeping_best(tmp_path: Path) -> None:
    idx = _index(tmp_path)
    fake = _FakeNER([
        {"text": "UPenn", "label": "university", "score": 0.9},
        {"text": "University of Pennsylvania School of Dental Medicine",
         "label": "dental school", "score": 0.95},
    ])
    ex = NERMentionExtractor(idx, model=fake)
    mentions = ex.extract("…")
    assert len(mentions) == 1
    assert mentions[0].canonical_id == "school:upenn"


def test_empty_text_safe(tmp_path: Path) -> None:
    ex = NERMentionExtractor(_index(tmp_path), model=_FakeNER([]))
    assert ex.extract("") == []
