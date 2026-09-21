"""Request/response schemas for ``/api/v1/sources/*`` (V1.5a connector backend)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.web.schemas.shared import SourceTier

Engine = Literal["postgres", "mysql", "sqlite", "neo4j", "local_file"]


class ConnectSourceRequest(BaseModel):
    """Body for ``POST /api/v1/sources`` (connect_data_source)."""

    model_config = ConfigDict(extra="forbid")

    engine: Engine
    config: dict[str, Any] = Field(default_factory=dict)
    tier: SourceTier = "L2"
    confirm_l1_immutable: bool = False
    label: str | None = None


class ConnectorSummary(BaseModel):
    """One connector row as returned by ``list_connectors``."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    engine: Engine
    tier: SourceTier
    status: str
    label: str | None = None
    connected_at: str | None = None
    last_pull_at: str | None = None


class SourcesListResponse(BaseModel):
    """``GET /api/v1/sources``."""

    model_config = ConfigDict(extra="forbid")

    connectors: list[ConnectorSummary] = Field(default_factory=list)


class SchemaDiscoveryResponse(BaseModel):
    """``POST /api/v1/sources/{source_id}/discover`` or
    ``GET /api/v1/sources/{source_id}/schema``."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    source_id: str
    discovered_schema: dict[str, Any] = Field(default_factory=dict)


class MappingDecision(BaseModel):
    """One row in the mapping commit payload."""

    model_config = ConfigDict(extra="forbid")

    table_or_column: str
    target_node_or_property: str
    confidence: float = 0.0
    decision: Literal["accept", "reject", "edit"] = "accept"


class CommitMappingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[MappingDecision] = Field(default_factory=list)
    dry_run: bool = False


class PullDeltaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    mode: Literal["delta", "full_resync"]
    rows_added: int = 0
    rows_updated: int = 0
    rows_deleted: int = 0


__all__ = [
    "CommitMappingRequest",
    "ConnectSourceRequest",
    "ConnectorSummary",
    "Engine",
    "MappingDecision",
    "PullDeltaResponse",
    "SchemaDiscoveryResponse",
    "SourcesListResponse",
]
