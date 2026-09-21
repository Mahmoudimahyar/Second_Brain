"""Tests for `src.ingestion.adapters.l1_excel.L1ExcelAdapter` (FR-1.2)."""

from __future__ import annotations

import dataclasses
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from openpyxl import Workbook

from src.ingestion.adapters.l1_excel import (
    L1Alias,
    L1ExcelAdapter,
    L1IngestResult,
    L1School,
    L1SchoolYearMetric,
    _col_letter,
)


def _make_synthetic_xlsx(path: Path, cycle: str = "2024-25") -> Path:
    """Build a tiny synthetic Report-2-like workbook for deterministic tests.

    Mirrors the ADEA multi-row layout: title row 1, subtitle row 2, header row
    on row 5 with the canonical 'School' column.
    """

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Tab1"

    ws["A1"] = "Table 1: Synthetic Tuition & Admissions"
    ws["A2"] = "Return to Table of Contents"
    ws["A3"] = "Source: ADEA - synthetic fixture"

    ws["A5"] = "School"
    ws["B5"] = "State"
    ws["C5"] = "City"
    ws["D5"] = "Tuition Resident"
    ws["E5"] = "Tuition Non-Resident"
    ws["F5"] = "Avg DAT AA"
    ws["G5"] = "Avg GPA Science"

    ws["A6"] = "Harvard School of Dental Medicine"
    ws["B6"] = "MA"
    ws["C6"] = "Boston"
    ws["D6"] = 79000
    ws["E6"] = 79000
    ws["F6"] = 22.5
    ws["G6"] = 3.8

    ws["A7"] = "New York University, College of Dentistry"
    ws["B7"] = "NY"
    ws["C7"] = "New York"
    ws["D7"] = "$94,108"
    ws["E7"] = "$94,108"
    ws["F7"] = 20.1
    ws["G7"] = 3.5

    ws["A8"] = "University of Pennsylvania School of Dental Medicine"
    ws["B8"] = "PA"
    ws["C8"] = "Philadelphia"
    ws["D8"] = 85000
    ws["E8"] = 85000
    ws["F8"] = 21.0
    ws["G8"] = 3.7

    ws["A9"] = "Total"
    ws["D9"] = 258000

    ws["A10"] = ""

    fname = f"SDE2_{cycle}.xlsx"
    out = path / fname
    wb.save(out)
    return out


def test_parse_extracts_schools_and_metrics(tmp_path: Path) -> None:
    payload = _make_synthetic_xlsx(tmp_path)
    adapter = L1ExcelAdapter(sqlite_path=tmp_path / "store.db")

    result = adapter.parse(payload)

    assert isinstance(result, L1IngestResult)
    assert result.cycle_year == "2024-25"
    assert len(result.schools) == 3
    names = [s.canonical_name for s in result.schools]
    assert "Harvard School of Dental Medicine" in names
    assert any("New York University" in n for n in names)
    assert any("Pennsylvania" in n for n in names)


def test_parse_skips_summary_row(tmp_path: Path) -> None:
    payload = _make_synthetic_xlsx(tmp_path)
    adapter = L1ExcelAdapter(sqlite_path=tmp_path / "store.db")

    result = adapter.parse(payload)

    assert not any(s.canonical_name.lower() == "total" for s in result.schools)


def test_parse_assigns_deterministic_canonical_ids(tmp_path: Path) -> None:
    payload = _make_synthetic_xlsx(tmp_path)
    adapter = L1ExcelAdapter(sqlite_path=tmp_path / "store.db")

    result_a = adapter.parse(payload)
    result_b = adapter.parse(payload)

    ids_a = sorted(s.canonical_id for s in result_a.schools)
    ids_b = sorted(s.canonical_id for s in result_b.schools)
    assert ids_a == ids_b
    assert all(cid.startswith("school:") for cid in ids_a)


def test_parse_extracts_metrics_with_value_coercion(tmp_path: Path) -> None:
    payload = _make_synthetic_xlsx(tmp_path)
    adapter = L1ExcelAdapter(sqlite_path=tmp_path / "store.db")

    result = adapter.parse(payload)

    nyu = next(
        s for s in result.schools if "New York University" in s.canonical_name
    )
    nyu_metrics = [m for m in result.metrics if m.canonical_school_id == nyu.canonical_id]
    # Metric names are sheet-title-prefixed for cross-sheet uniqueness
    # (e.g., "Table 1: Synthetic Tuition & Admissions - Tuition Resident").
    by_name = {m.metric_name: m for m in nyu_metrics}
    tuition_resident = next(
        m for n, m in by_name.items() if "Tuition Resident" in n
    )
    avg_dat = next(
        m for n, m in by_name.items() if "Avg DAT AA" in n
    )
    assert tuition_resident.metric_value == pytest.approx(94108.0)
    assert avg_dat.metric_value == pytest.approx(20.1)


def test_parse_sets_cycle_aligned_validity_window(tmp_path: Path) -> None:
    payload = _make_synthetic_xlsx(tmp_path, cycle="2024-25")
    adapter = L1ExcelAdapter(sqlite_path=tmp_path / "store.db")

    result = adapter.parse(payload)

    sample = result.metrics[0]
    assert sample.t_valid_from == datetime(2024, 9, 1, tzinfo=UTC)
    assert sample.t_valid_to == datetime(2025, 8, 31, tzinfo=UTC)


def test_parse_emits_alias_for_every_school(tmp_path: Path) -> None:
    payload = _make_synthetic_xlsx(tmp_path)
    adapter = L1ExcelAdapter(sqlite_path=tmp_path / "store.db")

    result = adapter.parse(payload)

    assert len(result.aliases) == len(result.schools)
    by_canonical = {a.canonical_id: a for a in result.aliases}
    for s in result.schools:
        assert s.canonical_id in by_canonical
        assert by_canonical[s.canonical_id].alias_text == s.canonical_name
        assert by_canonical[s.canonical_id].confidence == 1.0


def test_parse_raises_on_filename_without_cycle(tmp_path: Path) -> None:
    bad = tmp_path / "no_cycle.xlsx"
    wb = Workbook()
    wb.save(bad)
    adapter = L1ExcelAdapter(sqlite_path=tmp_path / "store.db")

    with pytest.raises(ValueError, match="Cannot infer cycle"):
        adapter.parse(bad)


def test_persist_writes_to_sqlite(tmp_path: Path) -> None:
    payload = _make_synthetic_xlsx(tmp_path)
    db_path = tmp_path / "store.db"
    adapter = L1ExcelAdapter(sqlite_path=db_path)

    result = adapter.parse(payload)
    adapter.persist(result, source_dump_id="dump:test123")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    schools = conn.execute("SELECT * FROM l1_school ORDER BY canonical_id").fetchall()
    metrics = conn.execute(
        "SELECT * FROM l1_school_year_metric ORDER BY metric_id",
    ).fetchall()
    aliases = conn.execute("SELECT * FROM alias ORDER BY alias_id").fetchall()
    # Manual aliases (3 — one per school).
    manual_aliases = [a for a in aliases if a["alias_source"] == "manual"]
    discovered_aliases = [
        a for a in aliases if a["alias_source"].startswith("discovered_")
    ]
    conn.close()

    assert len(schools) == 3
    assert all(r["source_dump_id"] == "dump:test123" for r in schools)
    assert len(metrics) == len(result.metrics)
    assert all(r["cycle_year"] == "2024-25" for r in metrics)
    # 3 manual + N discovered expansions (NYU/Penn/Harvard pattern hits, etc.).
    assert len(manual_aliases) == 3
    assert len(discovered_aliases) > 0
    assert len(aliases) == len(manual_aliases) + len(discovered_aliases)


def test_persist_is_idempotent(tmp_path: Path) -> None:
    payload = _make_synthetic_xlsx(tmp_path)
    db_path = tmp_path / "store.db"
    adapter = L1ExcelAdapter(sqlite_path=db_path)

    result = adapter.parse(payload)
    adapter.persist(result, source_dump_id="dump:test123")
    first_alias_count = _count(db_path, "alias")
    adapter.persist(result, source_dump_id="dump:test123")
    second_alias_count = _count(db_path, "alias")

    conn = sqlite3.connect(db_path)
    school_count = conn.execute("SELECT COUNT(*) FROM l1_school").fetchone()[0]
    metric_count = conn.execute(
        "SELECT COUNT(*) FROM l1_school_year_metric",
    ).fetchone()[0]
    conn.close()

    assert school_count == 3
    assert metric_count == len(result.metrics)
    assert first_alias_count == second_alias_count  # idempotent


def _count(db_path: Path, table: str) -> int:
    conn = sqlite3.connect(db_path)
    n = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    conn.close()
    return n


def test_persist_updates_metric_value_on_reingest(tmp_path: Path) -> None:
    """Same metric_id with a different value: INSERT OR REPLACE keeps the newest."""

    payload = _make_synthetic_xlsx(tmp_path)
    db_path = tmp_path / "store.db"
    adapter = L1ExcelAdapter(sqlite_path=db_path)

    first = adapter.parse(payload)
    adapter.persist(first, source_dump_id="dump:v1")

    bumped = L1IngestResult(
        cycle_year=first.cycle_year,
        schools=first.schools,
        metrics=[
            L1SchoolYearMetric(
                metric_id=m.metric_id,
                canonical_school_id=m.canonical_school_id,
                cycle_year=m.cycle_year,
                metric_name=m.metric_name,
                metric_value=(m.metric_value or 0) + 1000,
                unit=m.unit,
                source_row=m.source_row,
                t_valid_from=m.t_valid_from,
                t_valid_to=m.t_valid_to,
            )
            for m in first.metrics
        ],
        aliases=first.aliases,
    )
    adapter.persist(bumped, source_dump_id="dump:v2")

    conn = sqlite3.connect(db_path)
    sample = conn.execute(
        "SELECT metric_value, source_dump_id "
        "FROM l1_school_year_metric WHERE metric_id = ?",
        (first.metrics[0].metric_id,),
    ).fetchone()
    conn.close()
    assert sample is not None
    assert sample[0] == pytest.approx((first.metrics[0].metric_value or 0) + 1000)
    assert sample[1] == "dump:v2"


def _make_sde1_style_xlsx(path: Path, cycle: str = "2023-24") -> Path:
    """SDE1 (Report 1) Programs/Enrollment layout: school column is the
    verbose 'United States, CODA-accredited Dental Schools' header rather
    than the bare 'School' alias used in SDE2."""

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Tab1"
    ws["A1"] = "Table 1: Description of Academic Programs"
    ws["A2"] = "Return to Table of Contents"
    ws["A3"] = "State / Country / Province"
    ws["B3"] = "United States, CODA-accredited Dental Schools"
    ws["C3"] = "Type of Term"
    ws["D3"] = "Length of Academic Year (Weeks)"
    ws["A4"] = "MA"
    ws["B4"] = "Harvard School of Dental Medicine"
    ws["C4"] = "Semester"
    ws["D4"] = 42
    ws["A5"] = "NY"
    ws["B5"] = "New York University, College of Dentistry"
    ws["C5"] = "Trimester"
    ws["D5"] = 45
    out = path / f"SDE1_{cycle}.xlsx"
    wb.save(out)
    return out


def test_parse_sde1_style_layout(tmp_path: Path) -> None:
    """GAP-045: SDE1 uses 'United States, CODA-accredited Dental Schools' as
    the school header. Adapter must accept substring 'dental schools' (case-
    insensitive) in addition to the exact SCHOOL_ALIASES tokens."""

    payload = _make_sde1_style_xlsx(tmp_path)
    sqlite_path = tmp_path / "store.db"
    adapter = L1ExcelAdapter(sqlite_path=sqlite_path)
    result = adapter.parse(payload)

    assert {s.canonical_name for s in result.schools} == {
        "Harvard School of Dental Medicine",
        "New York University, College of Dentistry",
    }
    metric_names = {m.metric_name for m in result.metrics}
    assert any("Length of Academic Year" in n for n in metric_names)


def _make_sde3_style_xlsx(path: Path, cycle: str = "2024-25") -> Path:
    """SDE3 (Report 3) Tab4 layout: per-school finance ranked by tuition.

    Header is "Dental School 1" (singular + suffix); first column is a
    Rank Order integer that must NOT be promoted to school_id.
    """

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Tab4"
    ws["A1"] = "Table 4: Schools Rank Ordered by Tuition"
    ws["A2"] = "Return to Table of Contents"
    ws["A3"] = "Rank Order"
    ws["B3"] = "Dental School 1"
    ws["C3"] = "Type of Support"
    ws["D3"] = "DDS"
    ws["E3"] = "Advanced"
    ws["A4"] = 1
    ws["B4"] = "New York University"
    ws["C4"] = "Private Nonprofit"
    ws["D4"] = 1510
    ws["E4"] = 142
    ws["A5"] = 2
    ws["B5"] = "Harvard School of Dental Medicine"
    ws["C5"] = "Private Nonprofit"
    ws["D5"] = 280
    ws["E5"] = 60
    out = path / f"SDE3_{cycle}_final.xlsx"
    wb.save(out)
    return out


def _make_sde3_anonymized_xlsx(path: Path, cycle: str = "2024-25") -> Path:
    """SDE3 Tab5+ layout: anonymized random codes instead of real names. Must
    be skipped — the rows can't be mapped to canonical schools."""

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Tab5"
    ws["A1"] = "Table 5: Schools Rank Ordered (Anonymized)"
    ws["A2"] = "Return to Table of Contents"
    ws["A3"] = "Rank Order"
    ws["B3"] = "Dental School (Random Code)"
    ws["C3"] = "Type of Support"
    ws["D3"] = "Tuition and Fees Per FTE"
    ws["A4"] = 1
    ws["B4"] = 4476
    ws["C4"] = "Private"
    ws["D4"] = 122083
    ws["A5"] = 2
    ws["B5"] = 4329
    ws["C5"] = "Private"
    ws["D5"] = 114346
    out = path / f"SDE3_{cycle}_anon.xlsx"
    wb.save(out)
    return out


def test_parse_sde3_style_per_school_layout(tmp_path: Path) -> None:
    """GAP-045 cont'd: SDE3 Tab4 'Dental School 1' header + per-school rows
    must produce real School records."""

    payload = _make_sde3_style_xlsx(tmp_path)
    adapter = L1ExcelAdapter(sqlite_path=tmp_path / "store.db")
    result = adapter.parse(payload)

    names = {s.canonical_name for s in result.schools}
    assert names == {"New York University", "Harvard School of Dental Medicine"}


def test_school_name_strips_footnote_markers(tmp_path: Path) -> None:
    """GAP-045 cont'd: ADEA Excel cells often carry footnote markers ("1",
    "3", "*") appended to the school name. Without normalization, these create
    duplicate canonical_ids across sheets / files for the same real-world
    school (e.g., `school:nyu` vs `school:nyu1`). Strip the markers before
    slugifying."""

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Tab1"
    ws["A1"] = "Table 1: Footnote-marker stress"
    ws["A2"] = "Return to Table of Contents"
    ws["A5"] = "School"
    ws["B5"] = "Tuition"
    ws["A6"] = "New York University"
    ws["B6"] = 90000
    ws["A7"] = "New York University1"
    ws["B7"] = 91000
    ws["A8"] = "New York University3"
    ws["B8"] = 92000
    ws["A9"] = "Harvard University*"
    ws["B9"] = 79000
    out = tmp_path / "SDE2_2024-25.xlsx"
    wb.save(out)

    adapter = L1ExcelAdapter(sqlite_path=tmp_path / "store.db")
    result = adapter.parse(out)

    # All four name-variants should collapse to two canonical schools.
    canonical_ids = {s.canonical_id for s in result.schools}
    assert canonical_ids == {
        "school:new_york_university", "school:harvard_university",
    }


def test_parse_sde3_skips_anonymized_random_codes(tmp_path: Path) -> None:
    """SDE3 Tab5+ uses numeric random codes for the school column. Adapter
    must skip those rows (no canonical mapping possible)."""

    payload = _make_sde3_anonymized_xlsx(tmp_path)
    adapter = L1ExcelAdapter(sqlite_path=tmp_path / "store.db")
    result = adapter.parse(payload)

    assert result.schools == []
    assert result.metrics == []


def test_parse_sde1_style_does_not_promote_state_header(tmp_path: Path) -> None:
    """Regression guard: 'State / Country / Province' (column A in SDE1)
    must not be mistaken for the school column even though it sits before
    the real school column."""

    payload = _make_sde1_style_xlsx(tmp_path)
    sqlite_path = tmp_path / "store.db"
    adapter = L1ExcelAdapter(sqlite_path=sqlite_path)
    result = adapter.parse(payload)

    # If the state column had been mis-picked as the school column, the
    # canonical_ids would be school:ma / school:ny, not the real names.
    assert not any(s.canonical_id in {"school:ma", "school:ny"} for s in result.schools)


def test_col_letter_handles_double_letter() -> None:
    assert _col_letter(0) == "A"
    assert _col_letter(1) == "B"
    assert _col_letter(25) == "Z"
    assert _col_letter(26) == "AA"
    assert _col_letter(27) == "AB"
    assert _col_letter(51) == "AZ"
    assert _col_letter(52) == "BA"


def test_dataclasses_are_frozen() -> None:
    s = L1School(
        canonical_id="school:test",
        canonical_name="Test",
        city=None,
        state=None,
        source_row="Sheet1!A1",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.canonical_name = "Other"  # type: ignore[misc]

    a = L1Alias(
        alias_text="Test", canonical_id="school:test",
        alias_source="manual", confidence=1.0,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.confidence = 0.5  # type: ignore[misc]
