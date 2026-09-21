"""Response schemas for ``/api/v1/graph/*`` (ADR-012 multi-level retrieval)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.web.schemas.shared import SourceTier

GraphLevel = Literal["A", "B", "C"]


class GraphQueryResultItem(BaseModel):
    """One ranked result row from any of the level-typed graph queries."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    node_type: str
    properties: dict[str, Any] = Field(default_factory=dict)
    source_tier: SourceTier
    rank: str
    references: list[str] = Field(default_factory=list)
    confidence: float
    t_valid_from: datetime | None = None
    t_valid_to: datetime | None = None
    path_explanation: list[dict[str, str]] = Field(default_factory=list)


class GraphLevelResponse(BaseModel):
    """Response from ``/api/v1/graph/{structural,clusters,analyzed}``."""

    model_config = ConfigDict(extra="forbid")

    level: GraphLevel
    results: list[GraphQueryResultItem] = Field(default_factory=list)


class GraphCrossLinksResponse(BaseModel):
    """Response from ``/api/v1/graph/crosslinks`` (SAME_AS scan)."""

    model_config = ConfigDict(extra="forbid")

    results: list[GraphQueryResultItem] = Field(default_factory=list)


__all__ = [
    "GraphCrossLinksResponse",
    "GraphLevel",
    "GraphLevelResponse",
    "GraphQueryResultItem",
]
