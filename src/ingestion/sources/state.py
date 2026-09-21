"""Per-source cursor + pull state for V1.5a Phase 6.

Adds `data_source_state` + `pulls` SQLite tables (per data.md). The registry
(Phase 4) tracks `data_sources` rows; this module tracks the *runtime* state
of each source — its current cursor, last pull stats, schema snapshot hash.

The Prefect flow at `flows/data_source_pull.py` is the operator-facing
entry point; this module is the persistence layer behind it.
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from src.ingestion.sources.base import CanonicalRecord, CursorState, DataSource
from src.shared.errors import ErrorCode, StructuredError
from src.shared.timestamps import from_iso, to_iso, utc_now

PullMode = Literal["delta", "full_resync"]
PullStatus = Literal["running", "ok", "errored", "cap_hit"]


class PullReceipt(BaseModel):
    """One row of the `pulls` audit table (per data.md §pulls)."""

    model_config = ConfigDict(extra="forbid")

    pull_id: str
    source_id: str
    mode: PullMode
    started_at: datetime
    finished_at: datetime | None
    status: PullStatus
    rows_pulled: int
    nodes_written: int
    edges_written: int
    crosslinks_proposed: int
    crosslinks_auto_linked: int
    crosslinks_hitl: int
    error_excerpt: str | None
    audit_log_ref: str | None


class DataSourceStateStore:
    """SQLite-backed cursor + pull-history for V1.5a connectors."""

    def __init__(self, sqlite_path: Path) -> None:
        self._sqlite_path = Path(sqlite_path)
        self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS data_source_state (
                    source_id            TEXT PRIMARY KEY,
                    cursor_table         TEXT,
                    cursor_column        TEXT,
                    cursor_value         TEXT,
                    last_full_resync_at  TEXT,
                    schema_snapshot_hash TEXT
                );

                CREATE TABLE IF NOT EXISTS pulls (
                    pull_id                TEXT PRIMARY KEY,
                    source_id              TEXT NOT NULL,
                    mode                   TEXT NOT NULL,
                    started_at             TEXT NOT NULL,
                    finished_at            TEXT,
                    status                 TEXT,
                    rows_pulled            INTEGER,
                    nodes_written          INTEGER,
                    edges_written          INTEGER,
                    crosslinks_proposed    INTEGER,
                    crosslinks_auto_linked INTEGER,
                    crosslinks_hitl        INTEGER,
                    error_excerpt          TEXT,
                    audit_log_ref          TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_pulls_source ON pulls(source_id);
                """,
            )

    # ------------------------------------------------------------------
    # Cursor API
    # ------------------------------------------------------------------

    def get_cursor(self, source_id: str) -> CursorState | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM data_source_state WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        if row is None or not row["cursor_column"]:
            return None
        return CursorState(
            cursor_table=row["cursor_table"],
            cursor_column=row["cursor_column"],
            cursor_value=row["cursor_value"],
            last_full_resync_at=from_iso(row["last_full_resync_at"])
            if row["last_full_resync_at"] else None,
        )

    def set_cursor(
        self,
        source_id: str,
        cursor: CursorState,
        *,
        is_full_resync: bool = False,
    ) -> None:
        full_resync_at = to_iso(utc_now()) if is_full_resync else None
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT source_id FROM data_source_state WHERE source_id = ?",
                (source_id,),
            ).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO data_source_state "
                    "(source_id, cursor_table, cursor_column, cursor_value, "
                    " last_full_resync_at, schema_snapshot_hash) "
                    "VALUES (?, ?, ?, ?, ?, NULL)",
                    (
                        source_id, cursor.cursor_table,
                        cursor.cursor_column, cursor.cursor_value,
                        full_resync_at,
                    ),
                )
            else:
                # Preserve the prior full-resync timestamp when we're just
                # advancing a delta cursor.
                conn.execute(
                    "UPDATE data_source_state "
                    "SET cursor_table = ?, cursor_column = ?, "
                    "    cursor_value = ?, "
                    "    last_full_resync_at = COALESCE(?, last_full_resync_at) "
                    "WHERE source_id = ?",
                    (
                        cursor.cursor_table, cursor.cursor_column,
                        cursor.cursor_value, full_resync_at, source_id,
                    ),
                )
            conn.commit()

    def reset_cursor(self, source_id: str) -> None:
        """Clear the cursor to force a full re-pull on next run."""

        with self._connect() as conn:
            conn.execute(
                "UPDATE data_source_state "
                "SET cursor_table = NULL, cursor_column = NULL, "
                "    cursor_value = NULL "
                "WHERE source_id = ?",
                (source_id,),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Pulls audit
    # ------------------------------------------------------------------

    def start_pull(
        self,
        source_id: str,
        *,
        mode: PullMode,
    ) -> PullReceipt:
        pull_id = f"pull:{uuid.uuid4().hex[:16]}"
        started = utc_now()
        receipt = PullReceipt(
            pull_id=pull_id,
            source_id=source_id,
            mode=mode,
            started_at=started,
            finished_at=None,
            status="running",
            rows_pulled=0,
            nodes_written=0,
            edges_written=0,
            crosslinks_proposed=0,
            crosslinks_auto_linked=0,
            crosslinks_hitl=0,
            error_excerpt=None,
            audit_log_ref=None,
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO pulls (pull_id, source_id, mode, started_at, "
                "status, rows_pulled, nodes_written, edges_written, "
                "crosslinks_proposed, crosslinks_auto_linked, "
                "crosslinks_hitl) VALUES (?, ?, ?, ?, 'running', 0, 0, 0, 0, 0, 0)",
                (pull_id, source_id, mode, to_iso(started)),
            )
            conn.commit()
        return receipt

    def finalize_pull(
        self,
        pull_id: str,
        *,
        status: PullStatus,
        rows_pulled: int = 0,
        nodes_written: int = 0,
        edges_written: int = 0,
        crosslinks_proposed: int = 0,
        crosslinks_auto_linked: int = 0,
        crosslinks_hitl: int = 0,
        error_excerpt: str | None = None,
        audit_log_ref: str | None = None,
    ) -> PullReceipt:
        finished = utc_now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE pulls SET finished_at = ?, status = ?, "
                "rows_pulled = ?, nodes_written = ?, edges_written = ?, "
                "crosslinks_proposed = ?, crosslinks_auto_linked = ?, "
                "crosslinks_hitl = ?, error_excerpt = ?, audit_log_ref = ? "
                "WHERE pull_id = ?",
                (
                    to_iso(finished), status,
                    rows_pulled, nodes_written, edges_written,
                    crosslinks_proposed, crosslinks_auto_linked,
                    crosslinks_hitl, error_excerpt, audit_log_ref, pull_id,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM pulls WHERE pull_id = ?", (pull_id,),
            ).fetchone()
        if row is None:
            raise StructuredError(
                ErrorCode.VALIDATION_FAILED,
                f"pull_id {pull_id} not found after finalize",
            )
        return _pull_row_to_receipt(row)

    def list_pulls(self, source_id: str, *, limit: int = 50) -> list[PullReceipt]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM pulls WHERE source_id = ? "
                "ORDER BY started_at DESC LIMIT ?",
                (source_id, int(limit)),
            ).fetchall()
        return [_pull_row_to_receipt(r) for r in rows]

    # ------------------------------------------------------------------
    # V1.5d: connector-level aggregate stats + cursor listing for the UI
    # ------------------------------------------------------------------

    def connector_stats(self, source_id: str) -> dict[str, int]:
        """Aggregate stats across all successful (``status='ok'``) pulls
        for ``source_id``. Returns zero-valued dict when no successful
        pulls exist — that's the honest state for a never-pulled source.
        """

        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(rows_pulled), 0)            AS rows_total, "
                "       COALESCE(SUM(nodes_written), 0)          AS nodes_total, "
                "       COALESCE(SUM(edges_written), 0)          AS edges_total, "
                "       COALESCE(SUM(crosslinks_proposed), 0)    AS crosslinks_proposed, "
                "       COALESCE(SUM(crosslinks_auto_linked), 0) AS crosslinks_auto, "
                "       COALESCE(SUM(crosslinks_hitl), 0)        AS crosslinks_hitl "
                "FROM pulls WHERE source_id = ? AND status = 'ok'",
                (source_id,),
            ).fetchone()
        if row is None:
            return {
                "rows_total": 0, "nodes_total": 0, "edges_total": 0,
                "cross_links": 0,
            }
        return {
            "rows_total": int(row["rows_total"] or 0),
            "nodes_total": int(row["nodes_total"] or 0),
            "edges_total": int(row["edges_total"] or 0),
            "cross_links": int(
                (row["crosslinks_auto"] or 0) + (row["crosslinks_hitl"] or 0),
            ),
        }

    def list_cursors(self, source_id: str) -> list[dict[str, str | None]]:
        """List cursor rows for the UI's CursorEditor. Today this is at
        most one row (per-source cursor); V1.6 introduces per-table
        cursors and this method will return one row per tracked table.
        """

        with self._connect() as conn:
            row = conn.execute(
                "SELECT cursor_table, cursor_column, cursor_value "
                "FROM data_source_state WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        if row is None or not row["cursor_column"]:
            return []
        return [{
            "table": row["cursor_table"] or "",
            "column": row["cursor_column"] or "",
            "high_water_mark": row["cursor_value"],
        }]


# ----------------------------------------------------------------------
# Orchestrated pull (used by Prefect flow + CLI)
# ----------------------------------------------------------------------


def pull_source(
    *,
    data_source: DataSource,
    state_store: DataSourceStateStore,
    mode: PullMode = "delta",
) -> tuple[PullReceipt, list[CanonicalRecord]]:
    """Run a single pull against a DataSource, recording cursor + pull row.

    Returns (final_receipt, records). The receipt is finalized with stats
    derived from the streamed records. The records are also returned so the
    caller can write them to the graph (downstream V1 builders/extractors).
    """

    receipt = state_store.start_pull(data_source.source_id, mode=mode)
    if mode == "full_resync":
        cursor: CursorState | None = None
    else:
        cursor = state_store.get_cursor(data_source.source_id)

    records: list[CanonicalRecord] = []
    try:
        data_source.open()
        try:
            for rec in data_source.pull_delta(cursor):
                records.append(rec)
            advanced = data_source.advance_cursor()
        finally:
            data_source.close()
    except Exception as e:
        excerpt = repr(e)[:512]
        return (
            state_store.finalize_pull(
                receipt.pull_id, status="errored",
                error_excerpt=excerpt,
            ),
            [],
        )

    if advanced is not None:
        state_store.set_cursor(
            data_source.source_id, advanced,
            is_full_resync=(mode == "full_resync"),
        )

    return (
        state_store.finalize_pull(
            receipt.pull_id,
            status="ok",
            rows_pulled=len(records),
            nodes_written=len(records),   # 1:1 in Phase 6 — graph writer in V1
            edges_written=0,
            crosslinks_proposed=0,
            crosslinks_auto_linked=0,
            crosslinks_hitl=0,
        ),
        records,
    )


def iter_pull_batches(
    records: list[CanonicalRecord], *, batch_size: int = 1000,
) -> Iterator[list[CanonicalRecord]]:
    """Convenience generator for downstream batched graph writes."""

    for i in range(0, len(records), batch_size):
        yield records[i : i + batch_size]


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _pull_row_to_receipt(row: sqlite3.Row) -> PullReceipt:
    return PullReceipt(
        pull_id=row["pull_id"],
        source_id=row["source_id"],
        mode=row["mode"],
        started_at=from_iso(row["started_at"]),
        finished_at=from_iso(row["finished_at"]) if row["finished_at"] else None,
        status=row["status"],
        rows_pulled=int(row["rows_pulled"] or 0),
        nodes_written=int(row["nodes_written"] or 0),
        edges_written=int(row["edges_written"] or 0),
        crosslinks_proposed=int(row["crosslinks_proposed"] or 0),
        crosslinks_auto_linked=int(row["crosslinks_auto_linked"] or 0),
        crosslinks_hitl=int(row["crosslinks_hitl"] or 0),
        error_excerpt=row["error_excerpt"],
        audit_log_ref=row["audit_log_ref"],
    )


__all__ = [
    "DataSourceStateStore",
    "PullMode",
    "PullReceipt",
    "PullStatus",
    "iter_pull_batches",
    "pull_source",
]
