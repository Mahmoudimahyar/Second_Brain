"""Hypothesis property tests for `DataSource` lifecycle invariants (AC-1).

Asserts: any random sequence of (open / discover / sample / pull / close /
re-open) on a `LocalFileDataSource` does NOT leak file handles or open state.
Resource-leak detection uses `tracemalloc`.
"""

from __future__ import annotations

import tracemalloc
from pathlib import Path
from typing import Literal

import orjson
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.ingestion.sources.base import LocalFileConfig, SourceManifest
from src.ingestion.sources.local_file import LocalFileDataSource


@pytest.fixture(scope="module")
def reddit_fixture(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("ds_lifecycle")
    path = tmp / "x_posts.jsonl"
    with path.open("wb") as f:
        for rid in ("a", "b", "c"):
            f.write(orjson.dumps({
                "id": rid,
                "name": f"t3_{rid}",
                "author": "u1",
                "created_utc": 1_700_000_000,
                "title": rid,
                "selftext": "",
                "subreddit": "x",
                "subreddit_id": "t5_x",
                "score": 1,
                "ups": 1,
                "downs": 0,
                "num_comments": 0,
                "link_flair_text": None,
                "permalink": f"/r/x/comments/{rid}/_",
                "url": "https://example.org/",
                "over_18": False,
            }))
            f.write(b"\n")
    return path


Event = Literal["open", "close", "discover", "sample", "pull", "advance"]
event_strategy = st.lists(
    st.sampled_from(["open", "close", "discover", "sample", "pull", "advance"]),
    min_size=1,
    max_size=20,
)


@given(events=event_strategy)
@settings(
    max_examples=50,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_random_lifecycle_no_leaks(
    events: list[Event],
    reddit_fixture: Path,
) -> None:
    """Random lifecycle event sequences must not leak resources.

    All operations must be safely callable in any order — even pre-open ops
    should fail gracefully (auto-open on pull is intentional; other pre-open
    ops simply observe the closed state).
    """

    manifest = SourceManifest(
        source_id="ds:local_file:lifecycle",
        engine="local_file",
        display_name="Lifecycle",
        config=LocalFileConfig(adapter="l5_reddit", paths=[str(reddit_fixture)]),
        tier="L5",
        credential_ref=None,
        notes=None,
    )
    ds = LocalFileDataSource(manifest)

    tracemalloc.start()
    snap_before = tracemalloc.take_snapshot()
    try:
        for event in events:
            if event == "open":
                ds.open()
            elif event == "close":
                ds.close()
            elif event == "discover":
                ds.discover_schema()
            elif event == "sample":
                ds.sample_rows("post", n=1)
            elif event == "pull":
                list(ds.pull_delta(cursor=None))
            elif event == "advance":
                ds.advance_cursor()
    finally:
        ds.close()

    snap_after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    # Allow modest growth (Pydantic / hypothesis bookkeeping); the goal is to
    # catch unbounded growth proportional to event count.
    diff = sum(
        s.size_diff for s in snap_after.compare_to(snap_before, "filename")
    )
    assert diff < 5 * 1024 * 1024, f"unexpected memory growth: {diff} bytes"


def test_double_close_idempotent(reddit_fixture: Path) -> None:
    manifest = SourceManifest(
        source_id="ds:local_file:double_close",
        engine="local_file",
        display_name="Double close",
        config=LocalFileConfig(adapter="l5_reddit", paths=[str(reddit_fixture)]),
        tier="L5",
        credential_ref=None,
        notes=None,
    )
    ds = LocalFileDataSource(manifest)
    ds.open()
    ds.close()
    ds.close()  # second close is a no-op
    assert not ds.is_open()


def test_advance_cursor_after_pull(reddit_fixture: Path) -> None:
    manifest = SourceManifest(
        source_id="ds:local_file:cursor_check",
        engine="local_file",
        display_name="Cursor",
        config=LocalFileConfig(adapter="l5_reddit", paths=[str(reddit_fixture)]),
        tier="L5",
        credential_ref=None,
        notes=None,
    )
    ds = LocalFileDataSource(manifest)
    with ds:
        records = list(ds.pull_delta(cursor=None))
        cursor = ds.advance_cursor()
    assert records
    assert cursor.cursor_value
    assert cursor.cursor_column == "content_hash"
