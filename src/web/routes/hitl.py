"""V1.5b — `/api/v1/hitl` routes wrapping V1 + V1.5a HITL queue."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Query

from src.hitl.queue import Decision, HITLQueue, ItemStatus
from src.shared.errors import ErrorCode, StructuredError
from src.web.paths import sqlite_path

router = APIRouter()


def _queue() -> HITLQueue:
    return HITLQueue(sqlite_path=sqlite_path())


@router.get("/inbox")
def inbox() -> dict[str, Any]:
    """Aggregate counts per item_type (FR-1.5b-4.1).

    Ensures the hitl_queue table exists by touching the queue first.
    """

    _queue()  # ensures hitl_queue schema is initialised
    import sqlite3  # noqa: PLC0415
    counts: dict[str, int] = {}
    with sqlite3.connect(sqlite_path()) as conn:
        rows = conn.execute(
            "SELECT item_type, COUNT(*) FROM hitl_queue "
            "WHERE status = ? GROUP BY item_type",
            (ItemStatus.PENDING.value,),
        ).fetchall()
    for item_type, count in rows:
        counts[str(item_type)] = int(count)
    return {"counts": counts, "total": sum(counts.values())}


@router.get("/{item_type}")
def list_items(
    item_type: str,
    limit: int = Query(20, ge=1, le=200),
    status: str = "pending",
) -> dict[str, Any]:
    """List items for a given item_type + status."""

    import json  # noqa: PLC0415
    import sqlite3  # noqa: PLC0415

    with sqlite3.connect(sqlite_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM hitl_queue "
            "WHERE item_type = ? AND status = ? "
            "ORDER BY rowid LIMIT ?",
            (item_type, status, int(limit)),
        ).fetchall()
    return {
        "items": [
            {
                "item_id": r["item_id"],
                "item_type": r["item_type"],
                "payload": json.loads(r["payload_json"]),
                "status": r["status"],
                "claimed_by": r["claimed_by"],
            }
            for r in rows
        ],
    }


@router.post("/{item_id}/claim")
def claim_item(
    item_id: str, reviewer: str = "operator",
) -> dict[str, Any]:
    queue = _queue()
    item = queue.pull(reviewer=reviewer)
    if item is None:
        return {"item": None}
    return {
        "item": {
            "item_id": item.item_id,
            "item_type": item.item_type,
            "payload": item.payload,
            "status": str(item.status),
        },
    }


@router.post("/{item_id}/commit")
def commit_item(
    item_id: str,
    body: Annotated[dict[str, Any], Body(...)],
) -> dict[str, Any]:
    queue = _queue()
    decision = Decision(
        verdict=str(body.get("verdict", "")),
        notes=str(body.get("notes", "")),
        extra=body.get("extra", {}) if isinstance(body.get("extra"), dict) else {},
    )
    escalate = bool(body.get("escalate", False))
    result = queue.commit(item_id, decision, escalate=escalate)
    if result is None:
        raise StructuredError(
            ErrorCode.VALIDATION_FAILED,
            f"hitl item {item_id} not found",
            context={"item_id": item_id},
        )
    return {
        "item_id": result.item_id,
        "status": str(result.status),
        "verdict": decision.verdict,
    }
