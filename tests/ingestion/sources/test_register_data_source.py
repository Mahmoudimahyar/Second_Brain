"""Tests for `IngestionService.register_data_source()` (FR-1.5a-1.2)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import orjson
import pytest

from src.ingestion.api import DumpManifest, IngestionService
from src.ingestion.sources.base import (
    LocalFileConfig,
    PostgresConfig,
    SourceManifest,
)
from src.ingestion.sources.local_file import LocalFileDataSource
from src.ingestion.sources.postgres import PostgresDataSource


@pytest.fixture
def reddit_fixture(tmp_path: Path) -> Path:
    path = tmp_path / "x_posts.jsonl"
    with path.open("wb") as f:
        f.write(orjson.dumps({
            "id": "a1",
            "name": "t3_a1",
            "author": "u1",
            "created_utc": 1_700_000_000,
            "title": "t",
            "selftext": "",
            "subreddit": "x",
            "subreddit_id": "t5_x",
            "score": 1,
            "ups": 1,
            "downs": 0,
            "num_comments": 0,
            "link_flair_text": None,
            "permalink": "/r/x/comments/a1/_",
            "url": "https://example.org/",
            "over_18": False,
        }))
        f.write(b"\n")
    return path


@pytest.fixture
def service(tmp_path: Path) -> IngestionService:
    return IngestionService(
        dumps_root=tmp_path / "dumps",
        sqlite_path=tmp_path / "engine.db",
    )


def test_register_data_source_local_file_returns_wrapper(
    service: IngestionService,
    reddit_fixture: Path,
) -> None:
    manifest = SourceManifest(
        source_id="ds:local_file:t",
        engine="local_file",
        display_name="T",
        config=LocalFileConfig(adapter="l5_reddit", paths=[str(reddit_fixture)]),
        tier="L5",
        credential_ref=None,
        notes=None,
    )
    ds = service.register_data_source(manifest)
    assert isinstance(ds, LocalFileDataSource)
    assert ds.source_id == "ds:local_file:t"
    assert ds.tier == "L5"


def test_register_data_source_postgres_returns_engine(
    service: IngestionService,
) -> None:
    """V1.5a Phase 2 ships the Postgres engine; register_data_source returns
    a `PostgresDataSource` without attempting to connect."""
    manifest = SourceManifest(
        source_id="ds:postgres:t",
        engine="postgres",
        display_name="T",
        config=PostgresConfig(
            host="localhost", database="x", user="x",
        ),
        tier="L2",
        credential_ref=None,
        notes=None,
    )
    ds = service.register_data_source(manifest)
    assert isinstance(ds, PostgresDataSource)
    assert ds.source_id == "ds:postgres:t"
    assert ds.tier == "L2"


def test_v1_register_dump_still_works(
    service: IngestionService,
    reddit_fixture: Path,
    tmp_path: Path,
) -> None:
    """V1's `register_dump` path is unchanged. Regression guard."""
    manifest = DumpManifest(
        source_name="V1 regression",
        source_tier="L5",
        rank_default="normal",
        license="internal",
        t_valid_range=(
            datetime(2020, 1, 1, tzinfo=UTC),
            datetime(2030, 1, 1, tzinfo=UTC),
        ),
    )
    receipt = service.register_dump("L5", manifest, [reddit_fixture])
    assert receipt.dump_id.startswith("dump:")
    assert receipt.duplicate_of is None
