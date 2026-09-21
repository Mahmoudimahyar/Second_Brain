"""Tests for V1.5b `/api/v1/settings` (feedback-loop policy + corpora)."""

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


def test_get_policy_returns_caps(client: TestClient) -> None:
    res = client.get("/api/v1/settings/feedback-loop/policy")
    assert res.status_code == 200
    body = res.json()
    assert body["caps"]["positive_examples_k"] == 4   # ADR-018 hard cap
    assert body["caps"]["blocklist_max"] == 50


def test_view_feedback_loop_empty(client: TestClient) -> None:
    res = client.get(
        "/api/v1/settings/feedback-loop",
        params={
            "corpus_id": "test_corpus",
            "prompt_template_id": "test_template",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["examples"] == []
    assert body["blocklist"] == []
    assert body["context_hash"]


def test_append_decision_then_visible(client: TestClient) -> None:
    payload = {
        "corpus_id": "c1",
        "item_type": "node_proposal",
        "pattern": "Sentiment:Frustration",
        "verdict": "accept",
        "decided_by": "mahyar",
        "prompt_template_id": "extract_sentiment",
    }
    res = client.post(
        "/api/v1/settings/feedback-loop/decisions", json=payload,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["verdict"] == "accept"

    view = client.get(
        "/api/v1/settings/feedback-loop",
        params={
            "corpus_id": "c1",
            "prompt_template_id": "extract_sentiment",
        },
    ).json()
    patterns = [e["pattern"] for e in view["examples"]]
    assert "Sentiment:Frustration" in patterns


def test_corpora_listing(client: TestClient) -> None:
    # Seed two corpora
    for corpus in ("c1", "c2"):
        client.post(
            "/api/v1/settings/feedback-loop/decisions",
            json={
                "corpus_id": corpus,
                "item_type": "np",
                "pattern": f"P_{corpus}",
                "verdict": "accept",
                "decided_by": "m",
            },
        )
    res = client.get("/api/v1/settings/corpora")
    assert res.status_code == 200
    ids = {c["corpus_id"] for c in res.json()["corpora"]}
    assert {"c1", "c2"} <= ids
