"""Tests for V1.5a Phase 6 — re-pull cadence + state persistence.

Covers AC-7 (idempotency) + FR-1.5a-6 + the Prefect flow scaffold (without
requiring a running Prefect server — the flow degrades gracefully).
"""

from __future__ import annotations

from pathlib import Path

import orjson
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.ingestion.api import IngestionService
from src.ingestion.sources.base import (
    CursorState,
    LocalFileConfig,
    SourceManifest,
)
from src.ingestion.sources.state import (
    DataSourceStateStore,
    pull_source,
)


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
def reddit_fixture(tmp_path: Path) -> Path:
    path = tmp_path / "x_posts.jsonl"
    with path.open("wb") as f:
        for rid in ("a", "b", "c"):
            f.write(orjson.dumps(_post(rid)))
            f.write(b"\n")
    return path


@pytest.fixture
def service(tmp_path: Path) -> IngestionService:
    return IngestionService(
        dumps_root=tmp_path / "dumps",
        sqlite_path=tmp_path / "engine.db",
    )


@pytest.fixture
def state_store(tmp_path: Path) -> DataSourceStateStore:
    return DataSourceStateStore(sqlite_path=tmp_path / "engine.db")


def _manifest(reddit_fixture: Path) -> SourceManifest:
    return SourceManifest(
        source_id="ds:pull_test",
        engine="local_file",
        display_name="T",
        config=LocalFileConfig(adapter="l5_reddit", paths=[str(reddit_fixture)]),
        tier="L5",
    )


# ----------------------------------------------------------------------
# Cursor persistence
# ----------------------------------------------------------------------


def test_cursor_round_trip(state_store: DataSourceStateStore) -> None:
    cursor = CursorState(
        cursor_table=None, cursor_column="content_hash", cursor_value="abc",
    )
    state_store.set_cursor("ds:1", cursor)
    revived = state_store.get_cursor("ds:1")
    assert revived == cursor


def test_cursor_update(state_store: DataSourceStateStore) -> None:
    state_store.set_cursor("ds:1", CursorState(
        cursor_column="content_hash", cursor_value="a"))
    state_store.set_cursor("ds:1", CursorState(
        cursor_column="content_hash", cursor_value="b"))
    revived = state_store.get_cursor("ds:1")
    assert revived is not None
    assert revived.cursor_value == "b"


def test_reset_cursor_forces_full_pull(
    state_store: DataSourceStateStore,
) -> None:
    state_store.set_cursor("ds:1", CursorState(
        cursor_column="content_hash", cursor_value="x"))
    state_store.reset_cursor("ds:1")
    assert state_store.get_cursor("ds:1") is None


def test_full_resync_sets_timestamp(
    state_store: DataSourceStateStore,
) -> None:
    state_store.set_cursor(
        "ds:1",
        CursorState(cursor_column="content_hash", cursor_value="x"),
        is_full_resync=True,
    )
    revived = state_store.get_cursor("ds:1")
    assert revived is not None
    assert revived.last_full_resync_at is not None


# ----------------------------------------------------------------------
# pull_source orchestration
# ----------------------------------------------------------------------


def test_pull_source_idempotent(
    service: IngestionService,
    reddit_fixture: Path,
    state_store: DataSourceStateStore,
) -> None:
    """AC-7 + FR-1.5a-6.2 — pull twice in a row with no source changes
    writes 0 records on the second pull."""
    manifest = _manifest(reddit_fixture)
    ds = service.register_data_source(manifest, actor="test")
    receipt1, records1 = pull_source(
        data_source=ds, state_store=state_store, mode="delta",
    )
    receipt2, records2 = pull_source(
        data_source=ds, state_store=state_store, mode="delta",
    )
    assert receipt1.status == "ok"
    assert receipt1.rows_pulled == len(records1) > 0
    assert receipt2.status == "ok"
    assert receipt2.rows_pulled == 0
    assert records2 == []


def test_pull_records_pull_audit_row(
    service: IngestionService,
    reddit_fixture: Path,
    state_store: DataSourceStateStore,
) -> None:
    manifest = _manifest(reddit_fixture)
    ds = service.register_data_source(manifest, actor="test")
    pull_source(data_source=ds, state_store=state_store, mode="delta")
    pulls = state_store.list_pulls("ds:pull_test")
    assert len(pulls) == 1
    assert pulls[0].status == "ok"
    assert pulls[0].mode == "delta"


def test_full_resync_pulls_everything_again(
    service: IngestionService,
    reddit_fixture: Path,
    state_store: DataSourceStateStore,
) -> None:
    manifest = _manifest(reddit_fixture)
    ds = service.register_data_source(manifest, actor="test")
    pull_source(data_source=ds, state_store=state_store, mode="delta")
    receipt, records = pull_source(
        data_source=ds, state_store=state_store, mode="full_resync",
    )
    assert records  # everything re-pulled
    assert receipt.mode == "full_resync"


def test_pull_failure_recorded(
    service: IngestionService,
    tmp_path: Path,
    state_store: DataSourceStateStore,
) -> None:
    """Missing payload → connector raises → state store records errored pull."""
    manifest = SourceManifest(
        source_id="ds:fail",
        engine="local_file",
        display_name="Will fail",
        config=LocalFileConfig(
            adapter="l5_reddit",
            paths=[str(tmp_path / "nonexistent.jsonl")],
        ),
        tier="L5",
    )
    ds = service.register_data_source(manifest, actor="test")
    receipt, records = pull_source(
        data_source=ds, state_store=state_store, mode="delta",
    )
    assert receipt.status == "errored"
    assert receipt.error_excerpt is not None
    assert records == []


# ----------------------------------------------------------------------
# Hypothesis property: random trajectories
# ----------------------------------------------------------------------


Event = st.sampled_from(["pull", "noop", "full_resync"])


@given(events=st.lists(Event, min_size=1, max_size=10))
@settings(
    max_examples=25,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_random_trajectories_remain_idempotent(
    tmp_path_factory: pytest.TempPathFactory,
    events: list[str],
) -> None:
    """NFR-1.5a-4 idempotency property — random sequences keep the invariant
    that the second of two consecutive 'noop' pulls writes 0 records.
    """
    tmp = tmp_path_factory.mktemp("hyp")
    fixture = tmp / "p.jsonl"
    with fixture.open("wb") as f:
        for r in ("a", "b"):
            f.write(orjson.dumps(_post(r)))
            f.write(b"\n")
    service = IngestionService(
        dumps_root=tmp / "dumps", sqlite_path=tmp / "engine.db",
    )
    state_store = DataSourceStateStore(sqlite_path=tmp / "engine.db")
    manifest = _manifest(fixture)
    ds = service.register_data_source(manifest, actor="hyp")

    last_was_delta_pull = False
    for event in events:
        if event in {"pull", "noop"}:
            receipt, _records = pull_source(
                data_source=ds, state_store=state_store, mode="delta",
            )
            if last_was_delta_pull:
                # Two consecutive delta pulls without source-changes →
                # second one is a no-op.
                assert receipt.rows_pulled == 0
            last_was_delta_pull = True
        elif event == "full_resync":
            pull_source(
                data_source=ds, state_store=state_store, mode="full_resync",
            )
            last_was_delta_pull = False


# ----------------------------------------------------------------------
# V1.5d A4 — connector_stats + list_cursors for the UI
# ----------------------------------------------------------------------


def test_connector_stats_zero_for_never_pulled(tmp_path: Path) -> None:
    store = DataSourceStateStore(sqlite_path=tmp_path / "state.db")
    assert store.connector_stats("src:never") == {
        "rows_total": 0,
        "nodes_total": 0,
        "edges_total": 0,
        "cross_links": 0,
    }


def test_connector_stats_sums_across_successful_pulls(tmp_path: Path) -> None:
    store = DataSourceStateStore(sqlite_path=tmp_path / "state.db")
    # Two successful pulls + one errored pull (must be excluded from stats).
    r1 = store.start_pull("src:x", mode="delta")
    store.finalize_pull(
        r1.pull_id, status="ok",
        rows_pulled=10, nodes_written=10, edges_written=3,
        crosslinks_proposed=2, crosslinks_auto_linked=1, crosslinks_hitl=1,
    )
    r2 = store.start_pull("src:x", mode="delta")
    store.finalize_pull(
        r2.pull_id, status="ok",
        rows_pulled=5, nodes_written=5, edges_written=2,
        crosslinks_proposed=0, crosslinks_auto_linked=0, crosslinks_hitl=0,
    )
    r3 = store.start_pull("src:x", mode="delta")
    store.finalize_pull(
        r3.pull_id, status="errored",
        rows_pulled=999, nodes_written=999, edges_written=999,
    )
    stats = store.connector_stats("src:x")
    assert stats == {
        "rows_total": 15,
        "nodes_total": 15,
        "edges_total": 5,
        # cross_links = auto + hitl (NOT proposed).
        "cross_links": 2,
    }


def test_list_cursors_empty_when_no_cursor_recorded(tmp_path: Path) -> None:
    store = DataSourceStateStore(sqlite_path=tmp_path / "state.db")
    assert store.list_cursors("src:x") == []


def test_list_cursors_returns_persisted_cursor(tmp_path: Path) -> None:
    store = DataSourceStateStore(sqlite_path=tmp_path / "state.db")
    store.set_cursor(
        "src:x",
        CursorState(
            cursor_table="posts",
            cursor_column="created_at",
            cursor_value="2026-05-20T00:00:00Z",
        ),
    )
    assert store.list_cursors("src:x") == [{
        "table": "posts",
        "column": "created_at",
        "high_water_mark": "2026-05-20T00:00:00Z",
    }]
