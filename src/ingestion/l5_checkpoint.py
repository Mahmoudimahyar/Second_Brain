"""Durable per-post checkpoint for crash-resilient L5 forum ingest.

A full-subreddit ingest is multi-hour and the workstation is crash-prone
(Q-028). This records which posts have been fully written to the graph, in a
SQLite table that survives a host crash (each batch commits after its graph
writes land). On re-run the ingest skips done posts and resumes from the last
committed batch — at most one batch (a few minutes) is ever recomputed, and the
graph writes are idempotent (Kùzu MERGE) so re-doing a batch is harmless.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from src.shared.timestamps import to_iso, utc_now


class L5IngestCheckpoint:
    """Tracks completed post ids per source (subreddit/file) in `store.db`."""

    def __init__(self, sqlite_path: Path, source_key: str) -> None:
        self._path = Path(sqlite_path)
        self._source = source_key
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_table()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def _ensure_table(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS l5_ingest_progress ("
                "source_key TEXT NOT NULL, post_id TEXT NOT NULL, "
                "batch INTEGER, done_utc TEXT, "
                "PRIMARY KEY (source_key, post_id))",
            )
            conn.commit()

    def done_post_ids(self) -> set[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT post_id FROM l5_ingest_progress WHERE source_key = ?",
                (self._source,),
            ).fetchall()
        return {str(r[0]) for r in rows}

    def count(self) -> int:
        with self._connect() as conn:
            (n,) = conn.execute(
                "SELECT COUNT(*) FROM l5_ingest_progress WHERE source_key = ?",
                (self._source,),
            ).fetchone()
        return int(n)

    def mark_done(self, post_ids: Iterable[str], batch: int) -> None:
        """Record a batch's posts as complete (call AFTER the graph writes land)."""
        now = to_iso(utc_now())
        with self._connect() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO l5_ingest_progress "
                "(source_key, post_id, batch, done_utc) VALUES (?, ?, ?, ?)",
                [(self._source, str(pid), batch, now) for pid in post_ids],
            )
            conn.commit()

    def remove(self, post_ids: Iterable[str]) -> int:
        """Drop specific post ids (used to reconcile away entries whose graph
        writes were lost in a crash). Returns the count removed."""
        ids = [str(p) for p in post_ids]
        if not ids:
            return 0
        with self._connect() as conn:
            conn.executemany(
                "DELETE FROM l5_ingest_progress WHERE source_key = ? AND post_id = ?",
                [(self._source, p) for p in ids],
            )
            conn.commit()
        return len(ids)

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM l5_ingest_progress WHERE source_key = ?", (self._source,),
            )
            conn.commit()
