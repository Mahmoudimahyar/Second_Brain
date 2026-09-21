"""V1.5b — `/api/v1/graph` routes per ADR-012 multi-level retrieval."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query

router = APIRouter()


def _service() -> Any:
    """Lazy-construct the V1 RetrievalService — avoids requiring a live
    graph DB at import time (so tests can mock). Uses the process-shared
    Kùzu Database handle (one lockholder per process; the ask agent shares
    it) with a fresh per-request Connection."""

    import os  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    from src.er.canonical_index import CanonicalIndex  # noqa: PLC0415
    from src.graph.kuzu_client import KuzuGraphClient  # noqa: PLC0415
    from src.retrieval.api import RetrievalService  # noqa: PLC0415
    from src.web.graph_db import shared_database  # noqa: PLC0415

    data_dir = Path(os.environ.get("SECBRAIN_DATA_DIR", "data"))
    graph = KuzuGraphClient(
        db_path=data_dir / "graph" / "kuzu.db", database=shared_database(),
    )
    index = CanonicalIndex(sqlite_path=data_dir / "sqlite" / "store.db")
    return RetrievalService(graph=graph, canonical_index=index), graph


@router.get("/structural")
def structural(
    query: str = "",
    as_of: datetime | None = None,
    traversal_depth: int = Query(2, ge=1, le=5),
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    svc, graph = _service()
    try:
        results = svc.query_graph_structural(
            query=query, as_of=as_of,
            traversal_depth=traversal_depth, limit=limit,
        )
        return {"level": "A", "results": [_serialize_qr(r) for r in results]}
    finally:
        graph.close()


@router.get("/clusters")
def clusters(
    query: str = "",
    as_of: datetime | None = None,
    limit: int = Query(200, ge=1, le=2000),
) -> dict[str, Any]:
    svc, graph = _service()
    try:
        results = svc.query_graph_clusters(
            query=query, as_of=as_of, limit=limit,
        )
        return {"level": "B", "results": [_serialize_qr(r) for r in results]}
    finally:
        graph.close()


@router.get("/analyzed")
def analyzed(
    query: str = "",
    source_tier_min: str | None = None,
    as_of: datetime | None = None,
    traversal_depth: int = Query(3, ge=1, le=5),
    include_anomalies: bool = False,
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    svc, graph = _service()
    try:
        results = svc.query_graph_analyzed(
            query=query,
            source_tier_min=source_tier_min,
            as_of=as_of,
            traversal_depth=traversal_depth,
            include_anomalies=include_anomalies,
            limit=limit,
        )
        return {"level": "C", "results": [_serialize_qr(r) for r in results]}
    finally:
        graph.close()


@router.get("/crosslinks")
def crosslinks(
    source_tier_min: str | None = None,
    as_of: datetime | None = None,
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    svc, graph = _service()
    try:
        results = svc.query_graph_crosslinks(
            source_tier_min=source_tier_min,
            as_of=as_of, limit=limit,
        )
        return {"results": [_serialize_qr(r) for r in results]}
    finally:
        graph.close()


def _serialize_qr(qr: Any) -> dict[str, Any]:
    """Serialize a `QueryResult` dataclass to JSON-safe dict."""

    return {
        "node_id": qr.node_id,
        "node_type": qr.node_type,
        "properties": qr.properties,
        "source_tier": qr.source_tier,
        "rank": qr.rank,
        "references": qr.references,
        "confidence": qr.confidence,
        "t_valid_from": (
            qr.t_valid_from.isoformat() if qr.t_valid_from else None
        ),
        "t_valid_to": (
            qr.t_valid_to.isoformat() if qr.t_valid_to else None
        ),
        "path_explanation": qr.path_explanation,
    }
