"""V1.5a data-source registry — persistence + tier-declaration enforcement.

Per FR-1.5a-4 + state-machine.md §1. Backed by SQLite tables
`data_sources` + `data_source_tier_history` + `connector_audit` (per data.md).

Responsibilities:
- Persist `DataSourceRow` (one per registered manifest).
- Enforce L1 confirmation gate on register + retier.
- Bitemporal tier history (`tier_history`, `tier_as_of`).
- Audit-log every tier-upgrade attempt (rejected + accepted).
- Detect multi-L1 collisions for downstream HITL escalation.
- Soft-disconnect (status='disconnected') without losing audit trail.

This module is the persistence backbone V1.5a Phase 7's MCP tools will sit
on top of.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from src.ingestion.sources.base import SourceManifest, SourceTier
from src.shared.errors import ErrorCode, StructuredError
from src.shared.timestamps import from_iso, to_iso, utc_now

# Status strings (per state-machine.md §1 data source lifecycle)
DataSourceStatus = Literal[
    "active", "paused", "errored", "disconnected",
]

# Structured-error message tokens (test-asserted)
L1_REQUIRES_CONFIRMATION = (
    "L1 tier requires confirm_l1_immutable=True per ADR-014"
)
INVALID_TIER_UPGRADE = "INVALID_TIER_UPGRADE"
MULTIPLE_L1_CLAIMS = "MULTIPLE_L1_CLAIMS"


class DataSourceRow(BaseModel):
    """Persistent row for `data_sources` SQLite table (per data.md)."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    engine: str
    display_name: str
    config_json: str             # never contains plaintext creds
    credential_ref: str | None
    tier: SourceTier
    l1_confirmed_at: datetime | None
    status: DataSourceStatus
    created_at: datetime
    created_by: str
    last_pull_at: datetime | None
    last_pull_status: str | None
    notes: str | None
    t_ingest_from: datetime
    t_ingest_to: datetime | None


class TierHistoryEntry(BaseModel):
    """One row of `data_source_tier_history` (bitemporal)."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    tier: SourceTier
    confirmed_at: datetime | None
    t_ingest_from: datetime
    t_ingest_to: datetime | None
    actor: str


class DataSourceRegistry:
    """SQLite-backed registry for V1.5a connectors.

    Single-writer assumed at V1.5 scale (per ADR-013 single-user local).
    """

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
                CREATE TABLE IF NOT EXISTS data_sources (
                    source_id        TEXT PRIMARY KEY,
                    engine           TEXT NOT NULL,
                    display_name     TEXT NOT NULL,
                    config_json      TEXT NOT NULL,
                    credential_ref   TEXT,
                    tier             TEXT NOT NULL,
                    l1_confirmed_at  TEXT,
                    status           TEXT NOT NULL,
                    created_at       TEXT NOT NULL,
                    created_by       TEXT NOT NULL,
                    last_pull_at     TEXT,
                    last_pull_status TEXT,
                    notes            TEXT,
                    t_ingest_from    TEXT NOT NULL,
                    t_ingest_to      TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_ds_status ON data_sources(status);
                CREATE INDEX IF NOT EXISTS idx_ds_tier ON data_sources(tier);

                CREATE TABLE IF NOT EXISTS data_source_tier_history (
                    history_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id       TEXT NOT NULL REFERENCES data_sources(source_id),
                    tier            TEXT NOT NULL,
                    confirmed_at    TEXT,
                    t_ingest_from   TEXT NOT NULL,
                    t_ingest_to     TEXT,
                    actor           TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tier_hist_source
                    ON data_source_tier_history(source_id);

                CREATE TABLE IF NOT EXISTS connector_audit (
                    audit_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id       TEXT,
                    kind            TEXT NOT NULL,
                    actor           TEXT NOT NULL,
                    outcome         TEXT NOT NULL,
                    before_state    TEXT,
                    after_state     TEXT,
                    reason          TEXT,
                    ts              TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_kind
                    ON connector_audit(kind);
                CREATE INDEX IF NOT EXISTS idx_audit_source
                    ON connector_audit(source_id);
                """,
            )

    # ------------------------------------------------------------------
    # Register / retier / disconnect
    # ------------------------------------------------------------------

    def register(
        self,
        manifest: SourceManifest,
        *,
        actor: str,
        confirm_l1_immutable: bool = False,
    ) -> DataSourceRow:
        """Persist a new data source, enforcing tier rules. Idempotent on
        repeat by `source_id` (returns the existing row unchanged).
        """

        existing = self._fetch(manifest.source_id)
        if existing is not None:
            return existing

        l1_confirmed_at: datetime | None = None
        if manifest.tier == "L1":
            if not confirm_l1_immutable:
                self._audit(
                    source_id=manifest.source_id,
                    kind="connector_tier_upgrade_attempt",
                    actor=actor,
                    outcome="rejected",
                    after_state="L1",
                    reason=L1_REQUIRES_CONFIRMATION,
                )
                raise StructuredError(
                    ErrorCode.L1_IMMUTABLE_REJECT,
                    f"{L1_REQUIRES_CONFIRMATION} (source_id={manifest.source_id})",
                    context={
                        "source_id": manifest.source_id,
                        "attempted_tier": "L1",
                    },
                )
            l1_confirmed_at = utc_now()
            self._audit(
                source_id=manifest.source_id,
                kind="connector_tier_upgrade_attempt",
                actor=actor,
                outcome="accepted",
                after_state="L1",
                reason="confirm_l1_immutable=True",
            )

        # Serialize config WITHOUT credentials. The manifest only ever
        # carries `credential_ref` (env-var name), so this is already safe,
        # but we route through model_dump_json to avoid any accidental
        # extra fields a future config subclass might add.
        cfg_serialized = manifest.config.model_dump_json()

        t_ingest_from = utc_now()
        row = DataSourceRow(
            source_id=manifest.source_id,
            engine=manifest.engine,
            display_name=manifest.display_name,
            config_json=cfg_serialized,
            credential_ref=manifest.credential_ref,
            tier=manifest.tier,
            l1_confirmed_at=l1_confirmed_at,
            status="active",
            created_at=t_ingest_from,
            created_by=actor,
            last_pull_at=None,
            last_pull_status=None,
            notes=manifest.notes,
            t_ingest_from=t_ingest_from,
            t_ingest_to=None,
        )

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO data_sources (source_id, engine, display_name, "
                "config_json, credential_ref, tier, l1_confirmed_at, status, "
                "created_at, created_by, last_pull_at, last_pull_status, "
                "notes, t_ingest_from, t_ingest_to) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row.source_id, row.engine, row.display_name,
                    row.config_json, row.credential_ref, row.tier,
                    _to_iso_or_none(row.l1_confirmed_at), row.status,
                    to_iso(row.created_at), row.created_by,
                    _to_iso_or_none(row.last_pull_at), row.last_pull_status,
                    row.notes, to_iso(row.t_ingest_from), None,
                ),
            )
            conn.execute(
                "INSERT INTO data_source_tier_history "
                "(source_id, tier, confirmed_at, t_ingest_from, t_ingest_to, actor) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    row.source_id, row.tier,
                    _to_iso_or_none(l1_confirmed_at),
                    to_iso(t_ingest_from), None, actor,
                ),
            )
            conn.commit()

        self._audit(
            source_id=row.source_id,
            kind="connector_connect",
            actor=actor,
            outcome="accepted",
            after_state=row.tier,
            reason=None,
        )
        return row

    def retier(
        self,
        *,
        source_id: str,
        new_tier: SourceTier,
        actor: str,
        confirm_l1_immutable: bool = False,
    ) -> DataSourceRow:
        """Change a source's tier — closes prior `t_ingest_to` + opens new.

        Per FR-1.5a-4.3: "Re-tiering a connector requires re-ingesting from
        scratch." The actual re-pull side is Phase 6 (cursor reset); this
        function ensures the bitemporal tier history is correct.
        """

        existing = self._fetch(source_id)
        if existing is None:
            raise StructuredError(
                ErrorCode.CONNECTOR_NOT_FOUND,
                f"data source not found: {source_id}",
                context={"source_id": source_id},
            )

        l1_confirmed_at: datetime | None = None
        if new_tier == "L1":
            if not confirm_l1_immutable:
                self._audit(
                    source_id=source_id,
                    kind="connector_tier_upgrade_attempt",
                    actor=actor,
                    outcome="rejected",
                    before_state=existing.tier,
                    after_state="L1",
                    reason=(
                        f"{INVALID_TIER_UPGRADE}: "
                        "retier-to-L1 requires confirm_l1_immutable=True"
                    ),
                )
                raise StructuredError(
                    ErrorCode.L1_IMMUTABLE_REJECT,
                    f"{INVALID_TIER_UPGRADE}: retier to L1 requires "
                    "confirm_l1_immutable=True (source_id="
                    f"{source_id})",
                    context={
                        "source_id": source_id,
                        "attempted_tier": "L1",
                    },
                )
            l1_confirmed_at = utc_now()

        now = utc_now()
        with self._connect() as conn:
            # Close prior tier history entry
            conn.execute(
                "UPDATE data_source_tier_history "
                "SET t_ingest_to = ? "
                "WHERE source_id = ? AND t_ingest_to IS NULL",
                (to_iso(now), source_id),
            )
            # Open a new tier history entry
            conn.execute(
                "INSERT INTO data_source_tier_history "
                "(source_id, tier, confirmed_at, t_ingest_from, t_ingest_to, actor) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    source_id, new_tier,
                    _to_iso_or_none(l1_confirmed_at),
                    to_iso(now), None, actor,
                ),
            )
            # Update the live data_sources row
            conn.execute(
                "UPDATE data_sources "
                "SET tier = ?, l1_confirmed_at = ? "
                "WHERE source_id = ?",
                (
                    new_tier, _to_iso_or_none(l1_confirmed_at), source_id,
                ),
            )
            conn.commit()

        self._audit(
            source_id=source_id,
            kind="connector_tier_upgrade_attempt",
            actor=actor,
            outcome="accepted",
            before_state=existing.tier,
            after_state=new_tier,
            reason="retier",
        )
        return self._fetch(source_id)  # type: ignore[return-value]

    def disconnect(
        self, source_id: str, *, actor: str, retain_graph: bool = True,
    ) -> DataSourceRow:
        existing = self._fetch(source_id)
        if existing is None:
            raise StructuredError(
                ErrorCode.CONNECTOR_NOT_FOUND,
                f"data source not found: {source_id}",
                context={"source_id": source_id},
            )
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE data_sources "
                "SET status = 'disconnected', t_ingest_to = ? "
                "WHERE source_id = ?",
                (to_iso(now), source_id),
            )
            conn.commit()
        self._audit(
            source_id=source_id,
            kind="connector_disconnect",
            actor=actor,
            outcome="accepted",
            before_state=existing.status,
            after_state="disconnected",
            reason=f"retain_graph={retain_graph}",
        )
        return self._fetch(source_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def get(self, source_id: str) -> DataSourceRow | None:
        return self._fetch(source_id)

    def list_active(self) -> list[DataSourceRow]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM data_sources WHERE status = 'active' "
                "ORDER BY created_at",
            ).fetchall()
        return [_row_to_pydantic(r) for r in rows]

    def list_all(self) -> list[DataSourceRow]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM data_sources ORDER BY created_at",
            ).fetchall()
        return [_row_to_pydantic(r) for r in rows]

    def tier_history(self, source_id: str) -> list[TierHistoryEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM data_source_tier_history "
                "WHERE source_id = ? ORDER BY history_id",
                (source_id,),
            ).fetchall()
        out: list[TierHistoryEntry] = []
        for r in rows:
            out.append(TierHistoryEntry(
                source_id=r["source_id"],
                tier=r["tier"],
                confirmed_at=_from_iso_or_none(r["confirmed_at"]),
                t_ingest_from=from_iso(r["t_ingest_from"]),
                t_ingest_to=_from_iso_or_none(r["t_ingest_to"]),
                actor=r["actor"],
            ))
        return out

    def tier_as_of(self, source_id: str, *, at: datetime) -> SourceTier | None:
        """Return the tier that was active for `source_id` at time `at`."""

        for entry in self.tier_history(source_id):
            if entry.t_ingest_from <= at and (
                entry.t_ingest_to is None or at < entry.t_ingest_to
            ):
                return entry.tier
        return None

    def detect_multi_l1_claims(self) -> list[str]:
        """Return human-readable detection lines for multi-L1 collisions.

        V1.5a Phase 4: registry-level surface only — it flags that >1 L1
        connectors are active. Per-claim collision resolution lands in
        Phase 5 (CrossGraphLinker / conflict resolver feed) and Phase 7
        (HITL `multi_l1_claims` item type).
        """

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT source_id FROM data_sources "
                "WHERE tier = 'L1' AND status = 'active'",
            ).fetchall()
        if len(rows) < 2:
            return []
        ids = [r["source_id"] for r in rows]
        return [
            f"{MULTIPLE_L1_CLAIMS}: active L1 connectors {ids!r} — "
            "downstream conflict resolver must escalate per-claim "
            "collisions to HITL",
        ]

    def audit_log_entries(
        self, *, kind: str | None = None, source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM connector_audit WHERE 1 = 1"
        args: list[Any] = []
        if kind is not None:
            sql += " AND kind = ?"
            args.append(kind)
        if source_id is not None:
            sql += " AND source_id = ?"
            args.append(source_id)
        sql += " ORDER BY audit_id"
        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _fetch(self, source_id: str) -> DataSourceRow | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM data_sources WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        return _row_to_pydantic(row) if row else None

    def _audit(
        self,
        *,
        source_id: str | None,
        kind: str,
        actor: str,
        outcome: str,
        before_state: str | None = None,
        after_state: str | None = None,
        reason: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO connector_audit "
                "(source_id, kind, actor, outcome, before_state, "
                "after_state, reason, ts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    source_id, kind, actor, outcome,
                    before_state, after_state, reason, to_iso(utc_now()),
                ),
            )
            conn.commit()


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _to_iso_or_none(dt: datetime | None) -> str | None:
    return None if dt is None else to_iso(dt)


def _from_iso_or_none(s: Any) -> datetime | None:
    return None if s is None else from_iso(str(s))


def _row_to_pydantic(row: sqlite3.Row) -> DataSourceRow:
    return DataSourceRow(
        source_id=row["source_id"],
        engine=row["engine"],
        display_name=row["display_name"],
        config_json=row["config_json"],
        credential_ref=row["credential_ref"],
        tier=row["tier"],
        l1_confirmed_at=_from_iso_or_none(row["l1_confirmed_at"]),
        status=row["status"],
        created_at=from_iso(row["created_at"]),
        created_by=row["created_by"],
        last_pull_at=_from_iso_or_none(row["last_pull_at"]),
        last_pull_status=row["last_pull_status"],
        notes=row["notes"],
        t_ingest_from=from_iso(row["t_ingest_from"]),
        t_ingest_to=_from_iso_or_none(row["t_ingest_to"]),
    )


__all__ = [
    "INVALID_TIER_UPGRADE",
    "L1_REQUIRES_CONFIRMATION",
    "MULTIPLE_L1_CLAIMS",
    "DataSourceRegistry",
    "DataSourceRow",
    "DataSourceStatus",
    "TierHistoryEntry",
]
