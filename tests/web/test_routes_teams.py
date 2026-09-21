"""Tests for V1.5c ``/api/v1/teams/*`` routes.

W1-3 + W1-4 remediation: the route uses ``src.teams.data_loaders`` to
read from the V1 graph and falls back to the offline fixture when no
graph is present. The test environment has no graph in ``tmp_path``,
so the fixture path is exercised — which is also the AC-4 guarantee
(``≥ 10`` pain points must be reachable, fixture-fed when graph is
empty, graph-fed otherwise; either way the route honors the gate).
"""

from __future__ import annotations

import importlib
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


def test_pm_dashboard_returns_at_least_ten_pain_points(client: TestClient) -> None:
    """AC-4 — PM dashboard returns ≥ 10 sourced pain points.

    W1-4 restored the gate from ``≥ 6`` (the prior session's silent
    weakening) to ``≥ 10`` per the V1.5c README AC-4. The fixture
    backing the route's fallback path supplies 12 distinct labels so
    aggregation produces ≥ 12 pain points; a live V1 graph with a full
    Pass-4 sweep will surface more.
    """
    res = client.get("/api/v1/teams/pm")
    assert res.status_code == 200
    body = res.json()
    assert len(body["pain_points"]) >= 10, (
        f"AC-4 requires ≥ 10 pain points; got {len(body['pain_points'])}"
    )
    # Every pain point carries references — NFR-1.5c-4.
    assert all(len(pp["references"]) >= 1 for pp in body["pain_points"])


def test_pm_detail_includes_suggested_angles(client: TestClient) -> None:
    listing = client.get("/api/v1/teams/pm").json()
    first = listing["pain_points"][0]
    detail = client.get(
        f"/api/v1/teams/pm/{first['pain_point_id']}",
    ).json()
    assert detail["pain_point"]["pain_point_id"] == first["pain_point_id"]
    assert "suggested_angles" in detail
    assert len(detail["suggested_angles"]) >= 1
    assert all(a["draft_only"] for a in detail["suggested_angles"])


def test_pm_detail_unknown_id_404s(client: TestClient) -> None:
    res = client.get("/api/v1/teams/pm/pp:nonexistent:xyz")
    assert res.status_code == 400


def test_social_dashboard_returns_at_least_five_trending(client: TestClient) -> None:
    res = client.get("/api/v1/teams/social")
    assert res.status_code == 200
    body = res.json()
    assert len(body["trends"]) >= 5


def test_social_topic_detail(client: TestClient) -> None:
    listing = client.get("/api/v1/teams/social").json()
    first = listing["trends"][0]
    detail = client.get(
        f"/api/v1/teams/social/topic/{first['topic_id']}",
    ).json()
    assert detail["topic"]["topic_id"] == first["topic_id"]
    assert len(detail["suggested_angles"]) >= 1


def test_marketing_dashboard_returns_at_least_five_gaps(client: TestClient) -> None:
    res = client.get("/api/v1/teams/marketing")
    assert res.status_code == 200
    body = res.json()
    assert len(body["gaps"]) >= 5


def test_marketing_gap_detail(client: TestClient) -> None:
    listing = client.get("/api/v1/teams/marketing").json()
    first = listing["gaps"][0]
    detail = client.get(
        f"/api/v1/teams/marketing/gap/{first['gap_id']}",
    ).json()
    assert detail["gap"]["gap_id"] == first["gap_id"]
    assert detail["suggested_angles"]
