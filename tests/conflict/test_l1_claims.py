"""Tests for L1-fact-as-Claim emission + subject canonicalization (ADR-026 anchor)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from src.conflict.l1_claims import (
    build_adea_metric_claims,
    build_db_fact_claims,
    canonicalize_subject,
    normalize_adea_predicate,
)
from src.conflict.pass4_resolution import resolve_pass4_conflicts
from src.conflict.resolver import ConflictResolver
from src.er.canonical_index import CanonicalIndex
from src.graph.client import Node
from src.graph.kuzu_client import KuzuGraphClient

_T1_RES = ("Table 1: United States Dental School Resident and Non-Resident "
           "Tuition by Class, 2024-25 - Resident")
_T1_NONRES = ("Table 1: United States Dental School Resident and Non-Resident "
              "Tuition by Class, 2024-25 - Non-Resident")


def test_normalize_adea_predicate() -> None:
    assert normalize_adea_predicate(_T1_RES) == "tuition_resident"
    assert normalize_adea_predicate(_T1_NONRES) == "tuition_nonresident"
    assert normalize_adea_predicate("Table 6: Predental Education - 4 Years") is None


def test_build_db_fact_claims_from_school_node(tmp_path: Path) -> None:
    g = KuzuGraphClient(db_path=tmp_path / "kuzu.db")
    g.upsert_node(Node(
        id="school:ucla", label="School", source_tier="L1",
        properties={"canonical_name": "UCLA", "avg_board_pass_rate": 92.0,
                    "interview_required": True, "degree_offered": "DDS"},
    ))
    claims = build_db_fact_claims(g, source_dump_id="l1:gold")
    preds = {c.properties["predicate"]: c.properties["value"] for c in claims}
    assert preds["board_pass_rate"] == 92.0
    assert preds["interview_required"] is True
    assert preds["degree_offered"] == "DDS"
    assert all(c.source_tier == "L1" and c.label == "Claim" for c in claims)
    assert all(c.properties["subject"] == "school:ucla" for c in claims)
    g.close()


def test_build_adea_metric_claims_latest_cycle_wins(tmp_path: Path) -> None:
    db = tmp_path / "store.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE l1_school_year_metric (canonical_school_id TEXT, "
        "cycle_year TEXT, metric_name TEXT, metric_value REAL)",
    )
    conn.executemany(
        "INSERT INTO l1_school_year_metric VALUES (?,?,?,?)",
        [
            ("school:ucla", "2023-24", _T1_RES, 40000.0),
            ("school:ucla", "2024-25", _T1_RES, 42000.0),     # newer -> wins
            ("school:ucla", "2024-25", _T1_NONRES, 76000.0),
            ("school:ucla", "2024-25", "Table 6: ... - 4 Years", 99.0),  # skipped
        ],
    )
    conn.commit()
    conn.close()
    claims = build_adea_metric_claims(db, source_dump_id="adea")
    by_pred = {c.properties["predicate"]: c.properties for c in claims}
    assert set(by_pred) == {"tuition_resident", "tuition_nonresident"}
    assert by_pred["tuition_resident"]["value"] == 42000.0       # latest cycle
    assert by_pred["tuition_resident"]["cycle_year"] == "2024-25"


def _canonical_index(tmp_path: Path) -> CanonicalIndex:
    db = tmp_path / "store.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE alias (alias_text TEXT, canonical_id TEXT)")
    conn.execute("CREATE TABLE l1_school (canonical_id TEXT, canonical_name TEXT)")
    conn.executemany("INSERT INTO alias VALUES (?,?)",
                     [("UCLA", "school:ucla"), ("ucla", "school:ucla")])
    conn.execute("INSERT INTO l1_school VALUES ('school:ucla','UCLA')")
    conn.commit()
    conn.close()
    return CanonicalIndex(sqlite_path=db)


def test_canonicalize_subject(tmp_path: Path) -> None:
    idx = _canonical_index(tmp_path)
    assert canonicalize_subject("UCLA", idx) == "school:ucla"
    assert canonicalize_subject("ucla", idx) == "school:ucla"         # case-insensitive
    assert canonicalize_subject("school:ucla", idx) == "school:ucla"  # already canonical
    assert canonicalize_subject("Nonsense School", idx) == "Nonsense School"  # passthrough


def test_organic_firing_l1_claim_vs_l5_raw_subject(tmp_path: Path) -> None:
    """The payoff: an L1 gold tuition claim + an L5 forum claim that names the
    school by raw alias ("UCLA") land in one group via canonicalization, and the
    current-L1 anchor invalidates the wrong forum claim."""
    idx = _canonical_index(tmp_path)
    g = KuzuGraphClient(db_path=tmp_path / "kuzu.db")
    # L1 gold claim (canonical subject).
    g.upsert_node(Node(
        id="claim:l1:school:ucla:tuition_resident", label="Claim", source_tier="L1",
        properties={"subject": "school:ucla", "predicate": "tuition_resident",
                    "value": "42000", "cycle_year": "2024-25", "credibility": 1.0},
    ))
    # L5 forum claim naming the school by raw alias.
    g.upsert_node(Node(
        id="claim:l5:post1", label="Claim", source_tier="L5",
        properties={"subject": "UCLA", "predicate": "tuition_resident",
                    "value": "70000", "cycle_year": "2025-26", "credibility": 0.5},
    ))
    report = resolve_pass4_conflicts(
        g, ConflictResolver(), ingest_time=datetime(2026, 5, 30, tzinfo=UTC),
        canonical_index=idx,
    )
    assert report.conflict_groups == 1            # the two claims grouped
    assert report.l1_clash == 1                   # current L1 protected the gold value
    assert g.get_node("claim:l5:post1").properties.get("resolution_status") == (
        "invalidated_by_official"
    )
    assert g.get_node("claim:l1:school:ucla:tuition_resident").properties.get(
        "resolution_status") is None              # L1 never mutated
    g.close()
