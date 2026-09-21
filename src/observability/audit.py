from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from src.shared.timestamps import from_iso, to_iso, utc_now

AuditKind = Literal["extraction", "retrieval", "hitl", "ingestion"]


@dataclass(frozen=True)
class AuditRow:
    audit_id: str
    kind: AuditKind
    ts: datetime
    fields: dict[str, Any]
    ttl_pinned: int | None


class AuditLog:
    """V1 audit log per FR-11.

    - FR-11.1: every Anthropic call → `kind="extraction"` with cache + cost fields.
    - FR-11.2: every retrieval call → `kind="retrieval"`.
    - FR-11.3: every HITL decision → `kind="hitl"`.
    - Plus `kind="ingestion"` for dump registrations.

    The `ttl_pinned` column MUST equal 3600 on extraction rows (FR-2.5 / GAP-031);
    a lint check enforces this in `src.observability.lint_ttl`.
    """

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
                CREATE TABLE IF NOT EXISTS audit_log (
                    audit_id     TEXT PRIMARY KEY,
                    kind         TEXT NOT NULL,
                    ts           TEXT NOT NULL,
                    fields_json  TEXT NOT NULL,
                    ttl_pinned   INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_audit_kind ON audit_log(kind);
                CREATE INDEX IF NOT EXISTS idx_audit_ts   ON audit_log(ts);
                """,
            )

    def log_extraction(self, **fields: Any) -> str:
        ttl = fields.get("ttl_pinned")
        if ttl != 3600:
            raise ValueError(
                f"extraction audit must have ttl_pinned=3600; got {ttl} (FR-2.5)",
            )
        return self._log("extraction", fields, ttl_pinned=ttl)

    def log_retrieval(self, **fields: Any) -> str:
        return self._log("retrieval", fields, ttl_pinned=None)

    def log_hitl(self, **fields: Any) -> str:
        return self._log("hitl", fields, ttl_pinned=None)

    def log_ingestion(self, **fields: Any) -> str:
        return self._log("ingestion", fields, ttl_pinned=None)

    def _log(
        self, kind: AuditKind, fields: dict[str, Any], *, ttl_pinned: int | None,
    ) -> str:
        audit_id = fields.get("audit_id") or f"audit:{uuid.uuid4().hex[:16]}"
        ts = fields.get("ts") or utc_now()
        ts_iso = to_iso(ts) if isinstance(ts, datetime) else str(ts)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO audit_log "
                "(audit_id, kind, ts, fields_json, ttl_pinned) VALUES (?, ?, ?, ?, ?)",
                (audit_id, kind, ts_iso, json.dumps(_jsonable(fields)), ttl_pinned),
            )
            conn.commit()
        return str(audit_id)

    def query(
        self,
        *,
        since: datetime | None = None,
        kind: AuditKind | None = None,
        limit: int = 1000,
    ) -> list[AuditRow]:
        clauses: list[str] = []
        params: list[Any] = []
        if since is not None:
            clauses.append("ts >= ?")
            params.append(to_iso(since))
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        sql = "SELECT * FROM audit_log"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY ts DESC LIMIT ?"
        params.append(int(limit))

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [
            AuditRow(
                audit_id=str(r["audit_id"]),
                kind=str(r["kind"]),  # type: ignore[arg-type]
                ts=from_iso(str(r["ts"])),
                fields=json.loads(r["fields_json"]),
                ttl_pinned=(int(r["ttl_pinned"]) if r["ttl_pinned"] is not None else None),
            )
            for r in rows
        ]

    def count(self, *, kind: AuditKind | None = None) -> int:
        with self._connect() as conn:
            if kind is None:
                row = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM audit_log WHERE kind = ?", (kind,),
                ).fetchone()
        return int(row[0]) if row else 0


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, datetime):
        return to_iso(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [_jsonable(v) for v in value]
    return str(value)
