"""Response schemas for ``/api/v1/hitl/*``."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HitlInboxResponse(BaseModel):
    """Response from ``GET /api/v1/hitl/inbox``."""

    model_config = ConfigDict(extra="forbid")

    counts: dict[str, int] = Field(default_factory=dict)
    total: int


class HitlItem(BaseModel):
    """One HITL queue item as returned by `GET /api/v1/hitl/{item_type}`."""

    model_config = ConfigDict(extra="forbid")

    item_id: str
    item_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str
    claimed_by: str | None = None


class HitlListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[HitlItem] = Field(default_factory=list)


class HitlClaimResponse(BaseModel):
    """Response from ``POST /api/v1/hitl/{item_id}/claim``."""

    model_config = ConfigDict(extra="forbid")

    item: HitlItem | None = None


class HitlCommitRequest(BaseModel):
    """Request body for ``POST /api/v1/hitl/{item_id}/commit``."""

    model_config = ConfigDict(extra="forbid")

    verdict: str
    notes: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)
    escalate: bool = False


class HitlCommitResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    status: str
    verdict: str


__all__ = [
    "HitlClaimResponse",
    "HitlCommitRequest",
    "HitlCommitResponse",
    "HitlInboxResponse",
    "HitlItem",
    "HitlListResponse",
]
