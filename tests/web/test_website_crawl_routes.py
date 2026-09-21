"""V1.6a Phase 8 — FastAPI route tests for /api/v1/ingest/web/*.

Failing-first: POST /api/v1/ingest/web/domains with domain='reddit.com'
returns 422 + DOMAIN_BLOCKED per ADR-019.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    # Point the web layer at a fresh per-test SQLite via SECBRAIN_DATA_DIR
    # (the real env var src.web.paths reads — see paths.py).
    monkeypatch.setenv("SECBRAIN_DATA_DIR", str(tmp_path))
    (tmp_path / "sqlite").mkdir(exist_ok=True)
    from src.web.app import create_app
    return TestClient(create_app())


def test_post_domains_blocked_returns_422(client: TestClient) -> None:
    """Failing-first per V1.6a plan.md Phase 8."""
    r = client.post(
        "/api/v1/ingest/web/domains",
        json={"domain": "reddit.com", "tier": "L2", "stage": "L0"},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error_code"] == "DOMAIN_BLOCKED"


def test_post_domains_invalid_cron_returns_422(client: TestClient) -> None:
    r = client.post(
        "/api/v1/ingest/web/domains",
        json={
            "domain": "adea.org", "tier": "L2", "stage": "L0",
            "cadence_cron": "not a cron",
        },
    )
    assert r.status_code == 422
    assert r.json()["error_code"] == "INVALID_CRON"


def test_post_domains_l1_without_confirm_returns_422(client: TestClient) -> None:
    r = client.post(
        "/api/v1/ingest/web/domains",
        json={
            "domain": "adea.org", "tier": "L1", "stage": "L0",
            "confirm_l1_immutable": False,
        },
    )
    assert r.status_code == 422
    assert r.json()["error_code"] == "L1_NOT_CONFIRMED"


def test_post_domain_valid_returns_201(client: TestClient) -> None:
    r = client.post(
        "/api/v1/ingest/web/domains",
        json={"domain": "adea.org", "tier": "L2", "stage": "L1"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["domain"] == "adea.org"
    assert body["tier"] == "L2"
    assert body["stage"] == "L1"
    assert body["status"] == "active"


def test_get_domains_returns_list(client: TestClient) -> None:
    client.post(
        "/api/v1/ingest/web/domains",
        json={"domain": "adea.org", "tier": "L2", "stage": "L0"},
    )
    client.post(
        "/api/v1/ingest/web/domains",
        json={"domain": "ada.org", "tier": "L2", "stage": "L0"},
    )
    r = client.get("/api/v1/ingest/web/domains")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert {d["domain"] for d in body["domains"]} == {"adea.org", "ada.org"}


def test_pause_resume_round_trip_via_api(client: TestClient) -> None:
    reg_r = client.post(
        "/api/v1/ingest/web/domains",
        json={"domain": "adea.org", "tier": "L2", "stage": "L0"},
    )
    domain_id = reg_r.json()["domain_id"]
    r = client.post(f"/api/v1/ingest/web/domains/{domain_id}/pause")
    assert r.status_code == 200
    assert r.json()["status"] == "paused"
    r = client.post(f"/api/v1/ingest/web/domains/{domain_id}/resume")
    assert r.status_code == 200
    assert r.json()["status"] == "active"


def test_delete_marks_deleted(client: TestClient) -> None:
    reg_r = client.post(
        "/api/v1/ingest/web/domains",
        json={"domain": "adea.org", "tier": "L2", "stage": "L0"},
    )
    domain_id = reg_r.json()["domain_id"]
    r = client.delete(f"/api/v1/ingest/web/domains/{domain_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "deleted"


def test_run_now_enqueues_job(client: TestClient) -> None:
    reg_r = client.post(
        "/api/v1/ingest/web/domains",
        json={"domain": "adea.org", "tier": "L2", "stage": "L0"},
    )
    domain_id = reg_r.json()["domain_id"]
    r = client.post(
        f"/api/v1/ingest/web/domains/{domain_id}/run-now",
        json={"force_full_refresh": False},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "queued"
    assert r.json()["trigger"] == "manual"


def test_get_blocklist_returns_seeds(client: TestClient) -> None:
    r = client.get("/api/v1/ingest/web/blocklist")
    assert r.status_code == 200
    body = r.json()
    assert "reddit.com" in body["forum_domains"]
    assert "twitter.com" in body["social_domains"]


def test_get_budget_returns_snapshot(client: TestClient) -> None:
    reg_r = client.post(
        "/api/v1/ingest/web/domains",
        json={"domain": "adea.org", "tier": "L2", "stage": "L2"},
    )
    domain_id = reg_r.json()["domain_id"]
    r = client.get(f"/api/v1/ingest/web/domains/{domain_id}/budget")
    assert r.status_code == 200
    body = r.json()
    assert body["domain_id"] == domain_id
    assert body["spent_month_usd"] == 0.0
    assert body["cap_usd"] == 5.0
