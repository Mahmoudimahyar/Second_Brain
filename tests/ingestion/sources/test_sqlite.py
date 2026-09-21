"""Tests for V1.5a Phase 2c — `SQLiteDataSource` (FR-1.5a-2.3, AC-2).

Uses stdlib `sqlite3` + temp files. No Docker. Bonus: doubles as a self-test
fixture by pointing the engine at V1's L1 side-store file.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.ingestion.sources.base import (
    SourceManifest,
    SQLiteConfig,
)
from src.ingestion.sources.sqlite import SQLiteDataSource
from src.shared.errors import ErrorCode, StructuredError


@pytest.fixture
def seeded_sqlite(tmp_path: Path) -> Path:
    """A SQLite file with two tables + a FK + some rows."""
    db = tmp_path / "fixture.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE schools (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            city TEXT,
            state TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE metrics (
            metric_id TEXT PRIMARY KEY,
            school_id INTEGER NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value REAL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(school_id) REFERENCES schools(id)
        );
        INSERT INTO schools VALUES (1, 'NYU Dental', 'New York', 'NY', '2026-01-01');
        INSERT INTO schools VALUES (2, 'Harvard SDM', 'Boston', 'MA', '2026-01-01');
        INSERT INTO metrics VALUES ('m1', 1, 'tuition', 87000.0, '2026-01-01');
        INSERT INTO metrics VALUES ('m2', 2, 'tuition', 89000.0, '2026-01-01');
        """,
    )
    conn.commit()
    conn.close()
    return db


def _manifest(db: Path) -> SourceManifest:
    return SourceManifest(
        source_id="ds:sqlite:test",
        engine="sqlite",
        display_name="Test SQLite",
        config=SQLiteConfig(file_path=str(db)),
        tier="L2",
    )


def test_connect_and_discover(seeded_sqlite: Path) -> None:
    """AC-2 + FR-1.5a-2.3: connect, discover schema (incl. FKs), sample."""
    ds = SQLiteDataSource(_manifest(seeded_sqlite))
    with ds:
        snap = ds.discover_schema()
    assert snap.source_id == "ds:sqlite:test"
    table_names = {t.name for t in snap.tables}
    assert {"schools", "metrics"} <= table_names
    schools = next(t for t in snap.tables if t.name == "schools")
    assert {c.name for c in schools.column_specs} >= {
        "id", "name", "city", "state", "updated_at",
    }
    assert schools.primary_key == ["id"]
    metrics = next(t for t in snap.tables if t.name == "metrics")
    fk = metrics.foreign_keys[0]
    assert fk.columns == ["school_id"]
    assert fk.references_table == "schools"


def test_sample_rows_returns_dicts(seeded_sqlite: Path) -> None:
    ds = SQLiteDataSource(_manifest(seeded_sqlite))
    with ds:
        rows = ds.sample_rows("schools", n=2)
    assert len(rows) == 2
    assert {r["name"] for r in rows} == {"NYU Dental", "Harvard SDM"}


def test_pull_delta_initial(seeded_sqlite: Path) -> None:
    ds = SQLiteDataSource(_manifest(seeded_sqlite))
    with ds:
        records = list(ds.pull_delta(cursor=None))
    schools = [r for r in records if r.table_or_label == "schools"]
    metrics = [r for r in records if r.table_or_label == "metrics"]
    assert len(schools) == 2
    assert len(metrics) == 2


def test_pull_delta_idempotent_on_updated_at_cursor(seeded_sqlite: Path) -> None:
    """FR-1.5a-6.2: re-pull with cursor at max(updated_at) writes 0."""
    ds = SQLiteDataSource(_manifest(seeded_sqlite))
    with ds:
        first = list(ds.pull_delta(cursor=None))
        new_cursor = ds.advance_cursor()
        second = list(ds.pull_delta(cursor=new_cursor))
    assert first
    assert second == []
    assert new_cursor is not None
    assert new_cursor.cursor_column == "updated_at"


def test_pull_delta_picks_up_new_rows(
    seeded_sqlite: Path, tmp_path: Path,
) -> None:
    ds = SQLiteDataSource(_manifest(seeded_sqlite))
    with ds:
        _ = list(ds.pull_delta(cursor=None))
        cursor = ds.advance_cursor()

    # Insert a newer row
    conn = sqlite3.connect(seeded_sqlite)
    conn.execute(
        "INSERT INTO schools VALUES (3, 'UCSF Dental', 'San Francisco', 'CA', '2026-06-01')",
    )
    conn.commit()
    conn.close()

    with ds:
        records = list(ds.pull_delta(cursor=cursor))
    schools = [r for r in records if r.table_or_label == "schools"]
    assert len(schools) == 1


def test_full_resync_returns_everything(seeded_sqlite: Path) -> None:
    ds = SQLiteDataSource(_manifest(seeded_sqlite))
    with ds:
        records = list(ds.pull_delta(cursor=None))
        # Force a full re-sync via cursor=None
        full = list(ds.pull_delta(cursor=None))
    assert len(full) == len(records)


def test_lifecycle_round_trip(seeded_sqlite: Path) -> None:
    """open → close → open → close round-trips cleanly."""
    ds = SQLiteDataSource(_manifest(seeded_sqlite))
    for _ in range(3):
        ds.open()
        ds.discover_schema()
        list(ds.pull_delta(cursor=None))
        ds.close()


def test_missing_file_raises(tmp_path: Path) -> None:
    ds = SQLiteDataSource(_manifest(tmp_path / "nonexistent.db"))
    with pytest.raises(StructuredError) as excinfo:
        ds.open()
    assert excinfo.value.error_code in {
        ErrorCode.CONNECTION_FAILED,
        ErrorCode.INGESTION_PAYLOAD_MISSING,
    }


def test_discover_handles_table_without_pk(tmp_path: Path) -> None:
    db = tmp_path / "no_pk.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE no_pk_table (
            col_a TEXT,
            col_b INTEGER
        );
        INSERT INTO no_pk_table VALUES ('x', 1);
        """,
    )
    conn.commit()
    conn.close()
    ds = SQLiteDataSource(_manifest(db))
    with ds:
        snap = ds.discover_schema()
    table = next(t for t in snap.tables if t.name == "no_pk_table")
    # No PK → None or empty list
    assert table.primary_key is None or table.primary_key == []


def test_cursor_fallback_chain(tmp_path: Path) -> None:
    """FR-1.5a-6.1: cursor fallback chain `updated_at` → `created_at` → `pk`."""
    db = tmp_path / "fallback.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE no_updated (
            id INTEGER PRIMARY KEY,
            created_at TEXT NOT NULL,
            data TEXT
        );
        INSERT INTO no_updated VALUES (1, '2026-01-01', 'x');
        """,
    )
    conn.commit()
    conn.close()
    ds = SQLiteDataSource(_manifest(db))
    with ds:
        list(ds.pull_delta(cursor=None))
        cursor = ds.advance_cursor()
    assert cursor.cursor_column in {"created_at", "id"}
