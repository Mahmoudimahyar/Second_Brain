"""Tests for V1.5a Phase 6 — `flows/data_source_pull.py` Prefect flow.

The flow degrades gracefully without Prefect installed (no-op decorator) so
these tests run regardless. With Prefect available the same code path
becomes a real flow registration.
"""

from __future__ import annotations

from pathlib import Path

import orjson
import pytest

from flows.data_source_pull import data_source_pull_all
from src.ingestion.api import IngestionService
from src.ingestion.sources.base import LocalFileConfig, SourceManifest
from src.ingestion.sources.registry import DataSourceRegistry


def _post(rid: str) -> dict:
    return {
        "id": rid, "name": f"t3_{rid}", "author": "u",
        "created_utc": 1_700_000_000, "title": rid, "selftext": "",
        "subreddit": "x", "subreddit_id": "t5_x",
        "score": 1, "ups": 1, "downs": 0, "num_comments": 0,
        "link_flair_text": None,
        "permalink": f"/r/x/comments/{rid}/_",
        "url": "https://example.org/", "over_18": False,
    }


@pytest.fixture
def setup(tmp_path: Path) -> tuple[Path, Path]:
    fixture = tmp_path / "p.jsonl"
    with fixture.open("wb") as f:
        for r in ("a", "b"):
            f.write(orjson.dumps(_post(r)))
            f.write(b"\n")
    sqlite_path = tmp_path / "engine.db"
    service = IngestionService(
        dumps_root=tmp_path / "dumps",
        sqlite_path=sqlite_path,
    )
    manifest = SourceManifest(
        source_id="ds:flow_test",
        engine="local_file",
        display_name="Flow test",
        config=LocalFileConfig(adapter="l5_reddit", paths=[str(fixture)]),
        tier="L5",
    )
    service.register_data_source(manifest, actor="flow")
    return fixture, sqlite_path


def test_data_source_pull_all_runs_every_active_source(
    setup: tuple[Path, Path],
) -> None:
    """The flow iterates registered active sources and returns one receipt
    per source pulled."""
    _, sqlite_path = setup
    receipts = data_source_pull_all(sqlite_path=sqlite_path, mode="delta")
    assert len(receipts) == 1
    assert receipts[0].source_id == "ds:flow_test"
    assert receipts[0].status == "ok"


def test_data_source_pull_all_idempotent_across_runs(
    setup: tuple[Path, Path],
) -> None:
    """Two consecutive flow runs against unchanged data: second writes 0 rows."""
    _, sqlite_path = setup
    first = data_source_pull_all(sqlite_path=sqlite_path, mode="delta")
    second = data_source_pull_all(sqlite_path=sqlite_path, mode="delta")
    assert first[0].rows_pulled > 0
    assert second[0].rows_pulled == 0


def test_data_source_pull_all_skips_disconnected(
    tmp_path: Path,
) -> None:
    """Disconnected sources are not pulled by the all-sources flow."""
    fixture = tmp_path / "p.jsonl"
    with fixture.open("wb") as f:
        f.write(orjson.dumps(_post("x")))
        f.write(b"\n")
    sqlite_path = tmp_path / "engine.db"
    service = IngestionService(
        dumps_root=tmp_path / "dumps", sqlite_path=sqlite_path,
    )
    manifest = SourceManifest(
        source_id="ds:disconnected",
        engine="local_file",
        display_name="Will disconnect",
        config=LocalFileConfig(adapter="l5_reddit", paths=[str(fixture)]),
        tier="L5",
    )
    service.register_data_source(manifest, actor="t")

    registry = DataSourceRegistry(sqlite_path=sqlite_path)
    registry.disconnect("ds:disconnected", actor="t")

    receipts = data_source_pull_all(sqlite_path=sqlite_path, mode="delta")
    assert receipts == []
