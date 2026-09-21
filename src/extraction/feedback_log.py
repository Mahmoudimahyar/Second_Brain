"""V1.5b Phase 5 — append-only `feedback_log` (ADR-018).

Single source of truth for every HITL decision: cluster review, node/edge
proposal, alias accept/reject, cross-graph link, conflict resolution. Each
decision is content-hash-keyed, BGE-embedded, and never modified after
insertion (append-only invariant enforced via SQLite trigger).

Consumer: `FeedbackContextLoader` queries this log to build the active
context block for each Pass-4 BAML template invocation.
"""

from __future__ import annotations

import sqlite3
import struct
import uuid
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from src.shared.errors import ErrorCode, StructuredError
from src.shared.timestamps import from_iso, to_iso, utc_now

Verdict = Literal["accept", "reject", "refine", "defer"]


class FeedbackEntry(BaseModel):
    """One row of the `feedback_log` table (per ADR-018 schema)."""

    model_config = ConfigDict(extra="forbid")

    feedback_id: str
    corpus_id: str
    item_type: str
    pattern: str
    pattern_canonical: str
    verdict: Verdict
    refinement: str | None
    prompt_template_id: str | None
    decided_by: str
    decided_at: datetime
    applied_in_sweep_first: str | None
    review_session_id: str | None
    confidence_at_decision: float | None


class FeedbackLog:
    """Append-only SQLite-backed feedback log.

    The append-only invariant is enforced via SQL triggers (`OUTPUT ABORT`
    on UPDATE/DELETE) AND the Python API surface (no `update` / `delete`
    methods exposed). Embeddings are stored as packed binary blobs for
    space efficiency.
    """

    EMBEDDING_DIM: int = 384

    def __init__(self, sqlite_path: Path) -> None:
        self._sqlite_path = Path(sqlite_path)
        self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS feedback_log (
                    feedback_id              TEXT PRIMARY KEY,
                    corpus_id                TEXT NOT NULL,
                    item_type                TEXT NOT NULL,
                    pattern                  TEXT NOT NULL,
                    pattern_canonical        TEXT NOT NULL,
                    verdict                  TEXT NOT NULL,
                    refinement               TEXT,
                    pattern_embedding        BLOB,
                    prompt_template_id       TEXT,
                    decided_by               TEXT NOT NULL,
                    decided_at               TEXT NOT NULL,
                    applied_in_sweep_first   TEXT,
                    review_session_id        TEXT,
                    confidence_at_decision   REAL
                );
                CREATE INDEX IF NOT EXISTS idx_feedback_corpus
                    ON feedback_log(corpus_id);
                CREATE INDEX IF NOT EXISTS idx_feedback_template
                    ON feedback_log(prompt_template_id);
                CREATE INDEX IF NOT EXISTS idx_feedback_verdict
                    ON feedback_log(verdict);
                CREATE INDEX IF NOT EXISTS idx_feedback_decided_at
                    ON feedback_log(decided_at);

                -- Append-only triggers (ADR-018 invariant).
                CREATE TRIGGER IF NOT EXISTS feedback_log_no_update
                    BEFORE UPDATE ON feedback_log
                    BEGIN
                        SELECT RAISE(ABORT,
                            'feedback_log is append-only (ADR-018)');
                    END;
                CREATE TRIGGER IF NOT EXISTS feedback_log_no_delete
                    BEFORE DELETE ON feedback_log
                    BEGIN
                        SELECT RAISE(ABORT,
                            'feedback_log is append-only (ADR-018)');
                    END;
                """,
            )

    # ------------------------------------------------------------------
    # Append API (the only write surface)
    # ------------------------------------------------------------------

    def append(
        self,
        *,
        corpus_id: str,
        item_type: str,
        pattern: str,
        verdict: Verdict,
        decided_by: str,
        pattern_canonical: str | None = None,
        refinement: str | None = None,
        pattern_embedding: tuple[float, ...] | None = None,
        prompt_template_id: str | None = None,
        applied_in_sweep_first: str | None = None,
        review_session_id: str | None = None,
        confidence_at_decision: float | None = None,
    ) -> FeedbackEntry:
        if verdict not in {"accept", "reject", "refine", "defer"}:
            raise StructuredError(
                ErrorCode.VALIDATION_FAILED,
                f"invalid verdict: {verdict!r}",
            )
        if not pattern.strip():
            raise StructuredError(
                ErrorCode.VALIDATION_FAILED,
                "pattern must be non-empty",
            )
        entry = FeedbackEntry(
            feedback_id=f"fb:{uuid.uuid4().hex[:16]}",
            corpus_id=corpus_id,
            item_type=item_type,
            pattern=pattern,
            pattern_canonical=pattern_canonical or _canonicalize(pattern),
            verdict=verdict,
            refinement=refinement,
            prompt_template_id=prompt_template_id,
            decided_by=decided_by,
            decided_at=utc_now(),
            applied_in_sweep_first=applied_in_sweep_first,
            review_session_id=review_session_id,
            confidence_at_decision=confidence_at_decision,
        )
        emb_blob = _pack_embedding(pattern_embedding) if pattern_embedding else None
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO feedback_log "
                "(feedback_id, corpus_id, item_type, pattern, "
                " pattern_canonical, verdict, refinement, pattern_embedding, "
                " prompt_template_id, decided_by, decided_at, "
                " applied_in_sweep_first, review_session_id, "
                " confidence_at_decision) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.feedback_id, entry.corpus_id, entry.item_type,
                    entry.pattern, entry.pattern_canonical, entry.verdict,
                    entry.refinement, emb_blob,
                    entry.prompt_template_id, entry.decided_by,
                    to_iso(entry.decided_at),
                    entry.applied_in_sweep_first,
                    entry.review_session_id,
                    entry.confidence_at_decision,
                ),
            )
            conn.commit()
        return entry

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def get(self, feedback_id: str) -> FeedbackEntry | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM feedback_log WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        return _row_to_entry(row) if row else None

    def list_for_corpus(
        self,
        corpus_id: str,
        *,
        verdict: Verdict | None = None,
        prompt_template_id: str | None = None,
        limit: int | None = None,
    ) -> list[FeedbackEntry]:
        sql = "SELECT * FROM feedback_log WHERE corpus_id = ?"
        args: list[object] = [corpus_id]
        if verdict is not None:
            sql += " AND verdict = ?"
            args.append(verdict)
        if prompt_template_id is not None:
            sql += " AND (prompt_template_id IS NULL OR prompt_template_id = ?)"
            args.append(prompt_template_id)
        sql += " ORDER BY decided_at"
        if limit is not None:
            sql += " LIMIT ?"
            args.append(int(limit))
        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [_row_to_entry(r) for r in rows]

    def count(self, corpus_id: str | None = None) -> int:
        sql = "SELECT COUNT(*) FROM feedback_log"
        args: list[object] = []
        if corpus_id is not None:
            sql += " WHERE corpus_id = ?"
            args.append(corpus_id)
        with self._connect() as conn:
            row = conn.execute(sql, args).fetchone()
        return int(row[0]) if row else 0

    def embeddings_for(
        self,
        feedback_ids: Iterable[str],
    ) -> dict[str, tuple[float, ...] | None]:
        ids = list(feedback_ids)
        if not ids:
            return {}
        placeholders = ",".join(["?"] * len(ids))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT feedback_id, pattern_embedding FROM feedback_log "
                f"WHERE feedback_id IN ({placeholders})",
                ids,
            ).fetchall()
        return {
            str(r["feedback_id"]): (
                _unpack_embedding(r["pattern_embedding"])
                if r["pattern_embedding"] else None
            )
            for r in rows
        }


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _canonicalize(pattern: str) -> str:
    """Whitespace + casing normalization for pattern equality."""

    return " ".join(pattern.lower().split())


def _pack_embedding(vec: tuple[float, ...]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def _unpack_embedding(blob: bytes) -> tuple[float, ...]:
    n = len(blob) // 4
    return tuple(struct.unpack(f"<{n}f", blob))


def _row_to_entry(row: sqlite3.Row) -> FeedbackEntry:
    return FeedbackEntry(
        feedback_id=row["feedback_id"],
        corpus_id=row["corpus_id"],
        item_type=row["item_type"],
        pattern=row["pattern"],
        pattern_canonical=row["pattern_canonical"],
        verdict=row["verdict"],
        refinement=row["refinement"],
        prompt_template_id=row["prompt_template_id"],
        decided_by=row["decided_by"],
        decided_at=from_iso(row["decided_at"]),
        applied_in_sweep_first=row["applied_in_sweep_first"],
        review_session_id=row["review_session_id"],
        confidence_at_decision=row["confidence_at_decision"],
    )


__all__ = ["FeedbackEntry", "FeedbackLog", "Verdict"]
