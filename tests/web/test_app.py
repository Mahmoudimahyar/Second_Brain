"""Tests for V1.5b FastAPI app — health + structured error handling."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.web.app as app_module


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """A TestClient bound to a per-test SQLite workspace."""

    monkeypatch.setenv("SECBRAIN_DATA_DIR", str(tmp_path))
    (tmp_path / "sqlite").mkdir(exist_ok=True)
    importlib.reload(app_module)
    return TestClient(app_module.create_app())


def test_health(client: TestClient) -> None:
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"


def test_openapi_includes_v1_routes(client: TestClient) -> None:
    res = client.get("/openapi.json")
    assert res.status_code == 200
    spec = res.json()
    paths = set(spec["paths"].keys())
    # Sources surface
    assert "/api/v1/sources" in paths
    assert "/api/v1/sources/{source_id}" in paths
    assert "/api/v1/sources/{source_id}/discover" in paths
    assert "/api/v1/sources/{source_id}/mapping/suggest" in paths
    assert "/api/v1/sources/{source_id}/mapping/commit" in paths
    assert "/api/v1/sources/{source_id}/pull" in paths
    # Graph surface
    assert "/api/v1/graph/structural" in paths
    assert "/api/v1/graph/clusters" in paths
    assert "/api/v1/graph/analyzed" in paths
    assert "/api/v1/graph/crosslinks" in paths
    # HITL surface
    assert "/api/v1/hitl/inbox" in paths
    # Settings + audit surface
    assert "/api/v1/settings/feedback-loop" in paths
    assert "/api/v1/audit" in paths


def test_404_on_unknown_route(client: TestClient) -> None:
    res = client.get("/api/v1/nonexistent")
    assert res.status_code == 404


def test_structured_error_maps_to_404_for_missing_source(
    client: TestClient,
) -> None:
    res = client.get("/api/v1/sources/ds:does_not_exist")
    assert res.status_code == 404
    body = res.json()
    assert body["error_code"] == "CONNECTOR_NOT_FOUND"


def test_structured_error_maps_to_409_for_l1_reject(
    client: TestClient,
) -> None:
    res = client.post(
        "/api/v1/sources",
        json={
            "engine": "local_file",
            "display_name": "L1 reject",
            "source_id": "ds:l1_reject",
            "config": {
                "adapter": "l5_reddit",
                "paths": ["/nonexistent/path"],
            },
            "tier": "L1",
            # NO confirm_l1_immutable — should fail
        },
    )
    assert res.status_code == 409
    body = res.json()
    assert body["error_code"] == "L1_IMMUTABLE_REJECT"
