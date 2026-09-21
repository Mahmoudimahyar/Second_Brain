"""V1.5b — `/api/v1/sources` routes (V1.5a connector backend).

Wraps the V1.5a `IngestionService` + `DataSourceRegistry` + dispatch_connector_tool
surface so the Next.js UI can drive every connector flow.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Body

from src.ingestion.sources.state import DataSourceStateStore
from src.retrieval.connector_tools import dispatch_connector_tool
from src.shared.errors import ErrorCode, StructuredError
from src.web.paths import sqlite_path

router = APIRouter()


def _dispatch(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Typed wrapper around `dispatch_connector_tool` for the FastAPI surface."""

    return cast(dict[str, Any], dispatch_connector_tool(
        name, args, sqlite_path=sqlite_path(),
    ))


def _state_store() -> DataSourceStateStore:
    return DataSourceStateStore(sqlite_path=sqlite_path())


@router.post("")
def create_source(
    payload: Annotated[dict[str, Any], Body(...)],
) -> dict[str, Any]:
    """POST /api/v1/sources — connect_data_source."""
    return _dispatch("connect_data_source", payload)


@router.get("")
def list_sources(
    include_disconnected: bool = False,
) -> dict[str, Any]:
    return _dispatch(
        "list_connectors",
        {"include_disconnected": include_disconnected},
    )


@router.get("/{source_id}")
def get_source(source_id: str) -> dict[str, Any]:
    listing = _dispatch(
        "list_connectors", {"include_disconnected": True},
    )
    matches = [
        c for c in listing["connectors"] if c["source_id"] == source_id
    ]
    if not matches:
        raise StructuredError(
            ErrorCode.CONNECTOR_NOT_FOUND,
            f"source {source_id!r} not found",
            context={"source_id": source_id},
        )
    summary = cast(dict[str, Any], matches[0])
    # V1.5d: augment with aggregate stats + cursor listing. Stats are
    # zero when no successful pulls exist (honest); cursors are an
    # empty list when no cursor is recorded.
    store = _state_store()
    summary.update(store.connector_stats(source_id))
    summary["cursors"] = store.list_cursors(source_id)
    return summary


@router.delete("/{source_id}")
def delete_source(
    source_id: str, retain_graph: bool = True,
) -> dict[str, Any]:
    return _dispatch(
        "disconnect_data_source",
        {"source_id": source_id, "retain_graph": retain_graph},
    )


@router.post("/{source_id}/discover")
def discover_schema(
    source_id: str, refresh: bool = False,
) -> dict[str, Any]:
    return _dispatch(
        "discover_schema",
        {"source_id": source_id, "refresh": refresh},
    )


@router.get("/{source_id}/schema")
def get_schema(source_id: str) -> dict[str, Any]:
    # V1.5b reuses discover_schema for the GET (cached snapshot retrieval
    # is V1.6); semantics unchanged.
    return discover_schema(source_id, refresh=False)


@router.post("/{source_id}/mapping/suggest")
def suggest_mapping(source_id: str) -> dict[str, Any]:
    return _dispatch(
        "suggest_mapping",
        {"source_id": source_id},
    )


@router.post("/{source_id}/mapping/commit")
def commit_mapping(
    source_id: str,
    decisions: Annotated[list[dict[str, Any]], Body(...)],
    dry_run: bool = False,
) -> dict[str, Any]:
    return _dispatch(
        "commit_mapping",
        {"source_id": source_id, "decisions": decisions, "dry_run": dry_run},
    )


@router.post("/{source_id}/pull")
def pull_delta(
    source_id: str,
    mode: Literal["delta", "full_resync"] = "delta",
) -> dict[str, Any]:
    return _dispatch(
        "pull_delta",
        {"source_id": source_id, "mode": mode},
    )
