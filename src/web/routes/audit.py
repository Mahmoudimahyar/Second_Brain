"""V1.5b — `/api/v1/audit` routes (audit-log viewer)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from src.ingestion.sources.registry import DataSourceRegistry
from src.web.paths import sqlite_path

router = APIRouter()


@router.get("")
def list_audit(
    kind: str | None = Query(None),
    source_id: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
) -> dict[str, Any]:
    registry = DataSourceRegistry(sqlite_path=sqlite_path())
    rows = registry.audit_log_entries(kind=kind, source_id=source_id)
    return {"entries": rows[:limit], "total_returned": min(len(rows), limit)}


@router.get("/{audit_id}")
def get_audit(audit_id: int) -> dict[str, Any]:
    import sqlite3  # noqa: PLC0415
    with sqlite3.connect(sqlite_path()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM connector_audit WHERE audit_id = ?",
            (int(audit_id),),
        ).fetchone()
    if row is None:
        from src.shared.errors import ErrorCode, StructuredError  # noqa: PLC0415
        raise StructuredError(
            ErrorCode.VALIDATION_FAILED,
            f"audit_id {audit_id} not found",
            context={"audit_id": audit_id},
        )
    return dict(row)
