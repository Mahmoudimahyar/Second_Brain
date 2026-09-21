"""Ambiguity-aware, type-grounded resolution (school vs institution / state)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.er.canonical_index import CanonicalIndex


def _index(tmp_path: Path) -> CanonicalIndex:
    db = tmp_path / "store.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE alias (alias_text TEXT, canonical_id TEXT)")
    conn.execute(
        "CREATE TABLE l1_school (canonical_id TEXT, canonical_name TEXT, city TEXT, "
        "state TEXT, country TEXT, source_dump_id TEXT, created_utc TEXT)",
    )
    aliases = [
        ("NYU", "school:nyu_dental"),
        ("Michigan", "school:umich_dental"),
        ("Michigan", "institution:umich"),
        ("UT", "school:utenn_dental"),
        ("UT", "institution:utexas"),
        ("UMSD", "school:maryland_dental"),
        ("UMSD", "school:michigan_dental"),
        ("UMSD", "school:minnesota_dental"),
        ("University of Iowa", "institution:uiowa"),  # institution-only alias
    ]
    conn.executemany("INSERT INTO alias VALUES (?,?)", aliases)
    schools = [
        ("school:nyu_dental", "New York University College of Dentistry", "NY"),
        ("school:umich_dental", "University of Michigan School of Dentistry", "MI"),
        ("institution:umich", "University of Michigan", "Michigan"),  # full-name state
        ("school:utenn_dental", "University of Tennessee ... College of Dentistry", "TN"),
        ("institution:utexas", "University of Texas ... San Antonio", "TX"),
        ("school:maryland_dental", "University of Maryland School of Dentistry", "MD"),
        ("school:michigan_dental", "University of Michigan School of Dentistry", "MI"),
        ("school:minnesota_dental", "University of Minnesota School of Dentistry", "MN"),
        ("institution:uiowa", "University of Iowa", "IA"),
        ("school:uiowa_dental", "University of Iowa College of Dentistry", "IA"),
    ]
    conn.executemany(
        "INSERT INTO l1_school (canonical_id, canonical_name, state) VALUES (?,?,?)",
        schools,
    )
    conn.commit()
    conn.close()
    return CanonicalIndex(sqlite_path=db)


def test_unique_alias_high_confidence(tmp_path: Path) -> None:
    r = _index(tmp_path).resolve("NYU")
    assert r is not None and r.canonical_id == "school:nyu_dental"
    assert r.confidence == 1.0 and r.needs_review is False


def test_school_vs_institution_dental_context(tmp_path: Path) -> None:
    idx = _index(tmp_path)
    r = idx.resolve("Michigan", context="I just got into dental school here, DDS")
    assert r is not None and r.canonical_id == "school:umich_dental"
    assert r.reason.startswith("type")


def test_school_vs_institution_residency_context(tmp_path: Path) -> None:
    idx = _index(tmp_path)
    r = idx.resolve("Michigan", context="starting my OMFS residency program")
    assert r is not None and r.canonical_id == "institution:umich"


def test_dental_applicant_prior_when_no_context(tmp_path: Path) -> None:
    # r/predental etc. are dental-context by default → prefer the dental school.
    r = _index(tmp_path).resolve("Michigan", context="")
    assert r is not None and r.canonical_id == "school:umich_dental"


def test_cross_state_disambiguation(tmp_path: Path) -> None:
    idx = _index(tmp_path)
    # "UT" is Tennessee (dental) vs Texas (institution); a TN cue + dental context.
    r = idx.resolve("UT", context="moving to Tennessee for dental school")
    assert r is not None and r.canonical_id == "school:utenn_dental"


def test_irreducible_ambiguity_flags_for_review(tmp_path: Path) -> None:
    # UMSD → three different dental schools, no state cue → must NOT silently pick.
    r = _index(tmp_path).resolve("UMSD", context="applying to dental school")
    assert r is not None and r.needs_review is True
    assert r.reason == "ambiguous_unresolved" and r.confidence < 0.5


def test_state_resolves_the_ambiguous_three(tmp_path: Path) -> None:
    r = _index(tmp_path).resolve("UMSD", context="I'm staying in Minnesota for dental")
    assert r is not None and r.canonical_id == "school:minnesota_dental"
    assert r.needs_review is False


def test_institution_to_school_bridge(tmp_path: Path) -> None:
    # A bare-university institution hit is redirected to its sibling dental
    # school in dental context (Fix B).
    idx = _index(tmp_path)
    assert idx._institution_to_school.get("institution:uiowa") == "school:uiowa_dental"
    r = idx.resolve("University of Iowa", context="applying to dental school this cycle")
    assert r is not None and r.canonical_id == "school:uiowa_dental"
    assert "inst_to_school" in r.reason
    # In residency context the bridge is skipped (the institution is meant).
    r2 = idx.resolve("University of Iowa", context="my OMFS residency program")
    assert r2 is not None and r2.canonical_id == "institution:uiowa"


def test_unknown_alias_returns_none(tmp_path: Path) -> None:
    assert _index(tmp_path).resolve("Hogwarts") is None
