"""Shared response shapes used across `/api/v1/*` routes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SourceTier = Literal["L1", "L2", "L3", "L4", "L5"]


class ErrorEnvelope(BaseModel):
    """Standard error envelope for structured-error responses."""

    model_config = ConfigDict(extra="forbid")

    error_code: str
    message: str
    context: dict[str, Any] = Field(default_factory=dict)
