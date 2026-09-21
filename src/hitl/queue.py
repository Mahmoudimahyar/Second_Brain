from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from src.shared.timestamps import from_iso, to_iso, utc_now


class ItemStatus(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    COMMITTED = "committed"
    ESCALATED = "escalated"


@dataclass(frozen=True)
class HITLItem:
    item_id: str
    item_type: str            # "alias_match" / "conflict" / "new_type_proposal" / "judge_disagreement"
    payload: dict[str, Any]
    status: ItemStatus = ItemStatus.PENDING
    claimed_by: str | None = None
    claimed_at: datetime | None = None
    committed_at: datetime | None = None
    decision: Decision | None = None


@dataclass(frozen=True)
class Decision:
    verdict: str             # "accept" / "reject" / "escalate" / "tie_break_a" / ...
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class HITLQueue:
    """V1 HITL queue per FR-10. Lifecycle: pending → claimed → committed | escalated.

    Reviewers operate via the CLI (`src.hitl.cli`): `pull` claims the next
    pending item and writes a YAML file to `data/hitl/`; `commit` reads the
    edited YAML and finalizes the decision.
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
                CREATE TABLE IF NOT EXISTS hitl_queue (
                    item_id        TEXT PRIMARY KEY,
                    item_type      TEXT NOT NULL,
                    payload_json   TEXT NOT NULL,
                    status         TEXT NOT NULL,
                    claimed_by     TEXT,
                    claimed_at     TEXT,
                    committed_at   TEXT,
                    decision_json  TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_hitl_status ON hitl_queue(status);
                """,
            )

    def enqueue(self, *, item_type: str, payload: dict[str, Any]) -> str:
        item_id = f"hitl:{uuid.uuid4().hex[:16]}"
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO hitl_queue (item_id, item_type, payload_json, status) "
                "VALUES (?, ?, ?, ?)",
                (item_id, item_type, json.dumps(payload), ItemStatus.PENDING.value),
            )
            conn.commit()
        return item_id

    def pull(self, *, reviewer: str = "anonymous") -> HITLItem | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM hitl_queue WHERE status = ? ORDER BY rowid LIMIT 1",
                (ItemStatus.PENDING.value,),
            ).fetchone()
            if row is None:
                return None
            claimed_at = utc_now()
            conn.execute(
                "UPDATE hitl_queue SET status = ?, claimed_by = ?, claimed_at = ? "
                "WHERE item_id = ?",
                (ItemStatus.CLAIMED.value, reviewer, to_iso(claimed_at),
                 row["item_id"]),
            )
            conn.commit()
        return HITLItem(
            item_id=str(row["item_id"]),
            item_type=str(row["item_type"]),
            payload=json.loads(row["payload_json"]),
            status=ItemStatus.CLAIMED,
            claimed_by=reviewer,
            claimed_at=claimed_at,
        )

    def commit(
        self, item_id: str, decision: Decision, *,
        escalate: bool = False,
    ) -> HITLItem | None:
        target_status = (
            ItemStatus.ESCALATED if escalate else ItemStatus.COMMITTED
        )
        committed_at = utc_now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM hitl_queue WHERE item_id = ?", (item_id,),
            ).fetchone()
            if row is None:
                return None
            if row["status"] not in (ItemStatus.CLAIMED.value, ItemStatus.PENDING.value):
                # Already committed/escalated — idempotent no-op.
                return self.get(item_id)
            conn.execute(
                "UPDATE hitl_queue SET status = ?, committed_at = ?, decision_json = ? "
                "WHERE item_id = ?",
                (
                    target_status.value, to_iso(committed_at),
                    json.dumps({
                        "verdict": decision.verdict,
                        "notes": decision.notes,
                        "extra": decision.extra,
                    }),
                    item_id,
                ),
            )
            conn.commit()
        return self.get(item_id)

    def get(self, item_id: str) -> HITLItem | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM hitl_queue WHERE item_id = ?", (item_id,),
            ).fetchone()
        if row is None:
            return None
        decision = None
        if row["decision_json"]:
            d = json.loads(row["decision_json"])
            decision = Decision(
                verdict=d.get("verdict", ""),
                notes=d.get("notes", ""),
                extra=d.get("extra", {}),
            )
        return HITLItem(
            item_id=str(row["item_id"]),
            item_type=str(row["item_type"]),
            payload=json.loads(row["payload_json"]),
            status=ItemStatus(str(row["status"])),
            claimed_by=row["claimed_by"],
            claimed_at=_dt(row["claimed_at"]),
            committed_at=_dt(row["committed_at"]),
            decision=decision,
        )

    def list_items(
        self, *, status: ItemStatus | None = None, limit: int = 100,
    ) -> list[HITLItem]:
        sql = "SELECT * FROM hitl_queue"
        params: list[Any] = []
        if status is not None:
            sql += " WHERE status = ?"
            params.append(status.value)
        sql += " ORDER BY rowid DESC LIMIT ?"
        params.append(int(limit))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        items: list[HITLItem] = []
        for row in rows:
            item = self.get(str(row["item_id"]))
            if item is not None:
                items.append(item)
        return items


def _dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    return from_iso(str(value))
