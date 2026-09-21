"""W2-4 — UI-action audit middleware.

Every ``/api/v1/*`` request (except health + audit reads) writes a row
into the ``connector_audit`` SQLite table with a ``ui_*`` kind derived
from the route + method:

| Pattern | ``kind`` |
|---|---|
| ``GET /api/v1/health`` | (no audit — noise reduction) |
| ``GET /api/v1/audit/*`` | (no audit — would loop) |
| ``POST /api/v1/hitl/{item_id}/commit`` | ``ui_review_commit`` |
| ``POST /api/v1/hitl/{item_id}/batch`` | ``ui_batch_commit`` |
| ``POST/PATCH/PUT /api/v1/settings/*`` | ``ui_settings_update`` |
| ``GET /api/v1/* + query params`` | ``ui_filter_change`` |
| ``GET /api/v1/*`` (no params) | ``ui_view`` |
| Everything else | ``ui_view`` |

Closes gap-audit **MED-5** (V1.5b NFR-8 + FR-1.5b-8.3).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.web.paths import sqlite_path

log = structlog.get_logger(__name__)

# ----------------------------------------------------------------------
# Path → audit-kind classification
# ----------------------------------------------------------------------


def _audit_kind(request: Request) -> str | None:  # noqa: PLR0911 - each path branch is its own audit-kind rule
    """Classify a request into a ``ui_*`` audit kind. ``None`` skips audit."""

    path = request.url.path
    method = request.method.upper()

    # Health endpoints — never audited.
    if path == "/api/v1/health":
        return None
    # Audit reads — never audited (would generate noise looking at audit).
    if path.startswith("/api/v1/audit"):
        return None
    # Internal audit-view endpoint (W2-4) — audit it, but with ui_view kind.
    # (Not yet implemented; placeholder routing.)

    # HITL commits = ui_review_commit / ui_batch_commit
    if method == "POST" and "/hitl/" in path:
        if path.endswith("/commit"):
            return "ui_review_commit"
        if path.endswith("/batch"):
            return "ui_batch_commit"
        if path.endswith("/claim"):
            return "ui_select"

    # Settings mutations = ui_settings_update
    if method in {"POST", "PATCH", "PUT"} and "/settings" in path:
        return "ui_settings_update"

    # GET with query params = filter change (e.g., limit, status, kind)
    if method == "GET" and len(request.query_params) > 0:
        return "ui_filter_change"

    # Default: ui_view
    if method == "GET":
        return "ui_view"

    # POST/PATCH/PUT/DELETE not otherwise matched
    return "ui_view"


# ----------------------------------------------------------------------
# Audit row writer
# ----------------------------------------------------------------------


def _ensure_audit_schema(db_path_str: str) -> None:
    """Make sure ``connector_audit`` exists in the per-test sqlite db.

    ``DataSourceRegistry`` creates this table at registration time; the
    middleware may run before any connector is registered, so we
    duplicate the CREATE-IF-NOT-EXISTS here. Cheap idempotent operation.
    """

    with sqlite3.connect(db_path_str) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS connector_audit (
                audit_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id    TEXT,
                kind         TEXT NOT NULL,
                actor        TEXT NOT NULL,
                outcome      TEXT NOT NULL,
                before_state TEXT,
                after_state  TEXT,
                reason       TEXT,
                ts           TEXT NOT NULL
            )
            """,
        )


def write_ui_audit_row(
    *,
    kind: str,
    method: str,
    path: str,
    status_code: int,
    query_params: dict[str, str] | None,
    actor: str = "operator",
) -> None:
    """Persist one UI-action audit row to ``connector_audit``."""

    db_path = str(sqlite_path())
    _ensure_audit_schema(db_path)
    outcome = "ok" if status_code < 400 else "error"
    reason = json.dumps(query_params) if query_params else None
    after_state = f"{method} {path}"
    ts = datetime.now(UTC).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO connector_audit "
            "(source_id, kind, actor, outcome, before_state, "
            "after_state, reason, ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (None, kind, actor, outcome, None, after_state, reason, ts),
        )
        conn.commit()


# ----------------------------------------------------------------------
# Starlette middleware
# ----------------------------------------------------------------------


class UIAuditMiddleware(BaseHTTPMiddleware):
    """Writes a ``ui_*`` audit row for every ``/api/v1/*`` request.

    Runs AFTER the route handler so we know the HTTP status. Failures
    inside the audit write are logged but never propagate — auditing
    must not block the user response.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)

        # Only audit /api/v1/* paths; static / docs / OpenAPI passthrough.
        if not request.url.path.startswith("/api/v1/"):
            return response

        kind = _audit_kind(request)
        if kind is None:
            return response

        try:
            write_ui_audit_row(
                kind=kind,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                query_params=(
                    dict(request.query_params) if request.query_params else None
                ),
            )
        except Exception as exc:  # never block the response on audit failure
            log.warning(
                "ui_audit.write_failed",
                kind=kind,
                path=request.url.path,
                error=str(exc),
            )

        return response


__all__ = [
    "UIAuditMiddleware",
    "write_ui_audit_row",
]
