"""Tests for V1.5b `/api/v1/sources` routes."""

from __future__ import annotations

import importlib
from pathlib import Path

import orjson
import pytest
from fastapi.testclient import TestClient

import src.web.app as app_module


@pytest.fixture
def reddit_fixture(tmp_path: Path) -> Path:
    path = tmp_path / "x_posts.jsonl"
    with path.open("wb") as f:
        f.write(orjson.dumps({
            "id": "a1", "name": "t3_a1", "author": "u",
            "created_utc": 1_700_000_000, "title": "t", "selftext": "",
            "subreddit": "x", "subreddit_id": "t5_x",
            "score": 1, "ups": 1, "downs": 0, "num_comments": 0,
            "link_flair_text": None,
            "permalink": "/r/x/comments/a1/_",
            "url": "https://example.org/", "over_18": False,
        }))
        f.write(b"\n")
    return path


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("SECBRAIN_DATA_DIR", str(tmp_path))
    (tmp_path / "sqlite").mkdir(exist_ok=True)
    importlib.reload(app_module)
    return TestClient(app_module.create_app())


def _connect_local(client: TestClient, reddit_fixture: Path) -> str:
    payload = {
        "engine": "local_file",
        "display_name": "Test",
        "source_id": "ds:web_test",
        "config": {"adapter": "l5_reddit", "paths": [str(reddit_fixture)]},
        "tier": "L5",
    }
    res = client.post("/api/v1/sources", json=payload)
    assert res.status_code == 200, res.json()
    return res.json()["source_id"]


def test_connect_returns_receipt(
    client: TestClient, reddit_fixture: Path,
) -> None:
    sid = _connect_local(client, reddit_fixture)
    assert sid == "ds:web_test"


def test_list_excludes_disconnected(
    client: TestClient, reddit_fixture: Path,
) -> None:
    _connect_local(client, reddit_fixture)
    res = client.get("/api/v1/sources")
    assert res.status_code == 200
    body = res.json()
    ids = {c["source_id"] for c in body["connectors"]}
    assert "ds:web_test" in ids


def test_get_source_returns_summary(
    client: TestClient, reddit_fixture: Path,
) -> None:
    _connect_local(client, reddit_fixture)
    res = client.get("/api/v1/sources/ds:web_test")
    assert res.status_code == 200
    assert res.json()["source_id"] == "ds:web_test"


def test_discover_returns_schema(
    client: TestClient, reddit_fixture: Path,
) -> None:
    _connect_local(client, reddit_fixture)
    res = client.post("/api/v1/sources/ds:web_test/discover")
    assert res.status_code == 200
    body = res.json()
    table_names = {t["name"] for t in body["tables"]}
    assert {"post", "comment", "user"} <= table_names


def test_suggest_mapping(
    client: TestClient, reddit_fixture: Path,
) -> None:
    _connect_local(client, reddit_fixture)
    res = client.post("/api/v1/sources/ds:web_test/mapping/suggest")
    assert res.status_code == 200
    body = res.json()
    assert "per_table" in body


def test_pull_delta_then_idempotent(
    client: TestClient, reddit_fixture: Path,
) -> None:
    _connect_local(client, reddit_fixture)
    first = client.post("/api/v1/sources/ds:web_test/pull").json()
    assert first["rows_pulled"] > 0
    second = client.post("/api/v1/sources/ds:web_test/pull").json()
    assert second["rows_pulled"] == 0


def test_disconnect_works(
    client: TestClient, reddit_fixture: Path,
) -> None:
    _connect_local(client, reddit_fixture)
    res = client.delete("/api/v1/sources/ds:web_test")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "disconnected"
