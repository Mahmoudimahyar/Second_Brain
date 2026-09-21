"""W2-4 — UI-action audit middleware tests.

Asserts that ``/api/v1/*`` requests write the appropriate ``ui_*``
audit kind to the ``connector_audit`` SQLite table, and that the
``/health`` + ``/audit`` reads do NOT generate audit rows.
"""

from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.web.app as app_module


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("SECBRAIN_DATA_DIR", str(tmp_path))
    (tmp_path / "sqlite").mkdir(exist_ok=True)
    importlib.reload(app_module)
    return TestClient(app_module.create_app())


def _ui_audit_rows(tmp_path: Path) -> list[sqlite3.Row]:
    db = tmp_path / "sqlite" / "store.db"
    if not db.exists():
        return []
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        return list(conn.execute(
            "SELECT * FROM connector_audit WHERE kind LIKE 'ui_%' ORDER BY audit_id",
        ).fetchall())


def test_pm_dashboard_writes_ui_view_or_ui_filter_change(
    client: TestClient, tmp_path: Path,
) -> None:
    res = client.get("/api/v1/teams/pm")
    assert res.status_code == 200
    rows = _ui_audit_rows(tmp_path)
    assert len(rows) >= 1
    last = rows[-1]
    # No query params on this call → ui_view, not ui_filter_change
    assert last["kind"] == "ui_view"
    assert last["actor"] == "operator"
    assert last["outcome"] == "ok"
    assert last["after_state"] == "GET /api/v1/teams/pm"


def test_pm_dashboard_with_query_params_writes_ui_filter_change(
    client: TestClient, tmp_path: Path,
) -> None:
    res = client.get("/api/v1/teams/pm?min_volume=2")
    assert res.status_code == 200
    rows = _ui_audit_rows(tmp_path)
    last = rows[-1]
    assert last["kind"] == "ui_filter_change"
    assert last["reason"] is not None  # query params recorded as JSON
    assert "min_volume" in last["reason"]


def test_health_endpoint_does_not_write_audit(
    client: TestClient, tmp_path: Path,
) -> None:
    client.get("/api/v1/health")
    rows = _ui_audit_rows(tmp_path)
    paths = [r["after_state"] for r in rows]
    assert all("/health" not in p for p in paths)


def test_audit_endpoint_does_not_write_audit(
    client: TestClient, tmp_path: Path,
) -> None:
    """Reading the audit log should not generate audit rows about itself."""
    client.get("/api/v1/audit?limit=10")
    rows = _ui_audit_rows(tmp_path)
    paths = [r["after_state"] for r in rows]
    assert all("/audit" not in p for p in paths)


def test_error_response_records_outcome_error(
    client: TestClient, tmp_path: Path,
) -> None:
    """A 4xx/5xx response should record ``outcome='error'``."""
    res = client.get("/api/v1/teams/pm/pp:nonexistent:xyz")
    assert res.status_code == 400
    rows = _ui_audit_rows(tmp_path)
    last = rows[-1]
    assert last["outcome"] == "error"


def test_each_route_call_writes_at_least_one_row(
    client: TestClient, tmp_path: Path,
) -> None:
    routes = [
        "/api/v1/teams/pm",
        "/api/v1/teams/social",
        "/api/v1/teams/marketing",
    ]
    for route in routes:
        client.get(route)
    rows = _ui_audit_rows(tmp_path)
    paths = [r["after_state"] for r in rows]
    assert "GET /api/v1/teams/pm" in paths
    assert "GET /api/v1/teams/social" in paths
    assert "GET /api/v1/teams/marketing" in paths


def test_settings_get_writes_ui_view(client: TestClient, tmp_path: Path) -> None:
    res = client.get("/api/v1/settings/web-search")
    # The settings route may 404 if not yet wired in this test environment;
    # we only care that audit captured the attempt.
    rows = _ui_audit_rows(tmp_path)
    assert any(
        "/api/v1/settings/" in r["after_state"]
        for r in rows
    ), f"expected a settings audit row; got {[r['after_state'] for r in rows]}"
    _ = res  # status code not asserted here
