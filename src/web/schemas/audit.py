"""Response schemas for ``/api/v1/audit/*``."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AuditKind = Literal[
    # V1.5a — connector lifecycle
    "connector_connect",
    "connector_disconnect",
    "connector_tier_upgrade_attempt",
    "pull_delta",
    # V1.5b — UI surface (W2-4)
    "ui_view",
    "ui_select",
    "ui_filter_change",
    "ui_review_commit",
    "ui_batch_commit",
    "ui_settings_update",
    # V1.5c — web-verification cost / cap
    "web_search_cost",
    "web_search_cap_hit",
    # General catch-all
    "audit",
]


class AuditRow(BaseModel):
    """One audit log row as returned by ``GET /api/v1/audit``."""

    model_config = ConfigDict(extra="forbid")

    audit_id: str
    kind: AuditKind | str  # str fallback for forward compatibility
    actor: str
    ts: str
    context: dict[str, Any] = Field(default_factory=dict)


class AuditListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[AuditRow] = Field(default_factory=list)
    total: int = 0


class AuditViewRequest(BaseModel):
    """Body for ``POST /api/v1/audit/view`` — recorded by the
    ``useAuditPageView()`` React hook for SPA route mounts (W2-4)."""

    model_config = ConfigDict(extra="forbid")

    path: str
    actor: str = "operator"
    context: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "AuditKind",
    "AuditListResponse",
    "AuditRow",
    "AuditViewRequest",
]
