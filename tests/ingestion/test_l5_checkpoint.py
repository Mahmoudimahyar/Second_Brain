"""Tests for the crash-resilient L5 ingest checkpoint."""

from __future__ import annotations

from pathlib import Path

from src.ingestion.l5_checkpoint import L5IngestCheckpoint


def test_empty_checkpoint(tmp_path: Path) -> None:
    ck = L5IngestCheckpoint(tmp_path / "store.db", source_key="reddit_x")
    assert ck.done_post_ids() == set()
    assert ck.count() == 0


def test_mark_and_resume(tmp_path: Path) -> None:
    db = tmp_path / "store.db"
    ck = L5IngestCheckpoint(db, source_key="reddit_x")
    ck.mark_done(["p1", "p2", "p3"], batch=0)
    ck.mark_done(["p4"], batch=1)
    assert ck.done_post_ids() == {"p1", "p2", "p3", "p4"}
    assert ck.count() == 4
    # A fresh instance (simulating a re-run after a crash) sees the same progress.
    resumed = L5IngestCheckpoint(db, source_key="reddit_x")
    assert resumed.done_post_ids() == {"p1", "p2", "p3", "p4"}


def test_mark_done_is_idempotent(tmp_path: Path) -> None:
    ck = L5IngestCheckpoint(tmp_path / "store.db", source_key="reddit_x")
    ck.mark_done(["p1", "p2"], batch=0)
    ck.mark_done(["p1", "p2"], batch=0)   # re-done batch after a mid-batch crash
    assert ck.count() == 2


def test_source_key_isolation(tmp_path: Path) -> None:
    db = tmp_path / "store.db"
    a = L5IngestCheckpoint(db, source_key="reddit_predental")
    b = L5IngestCheckpoint(db, source_key="reddit_dentalschool")
    a.mark_done(["p1"], batch=0)
    assert a.done_post_ids() == {"p1"}
    assert b.done_post_ids() == set()       # different subreddit, separate progress


def test_remove_reconciles_phantom_entries(tmp_path: Path) -> None:
    ck = L5IngestCheckpoint(tmp_path / "store.db", source_key="reddit_x")
    ck.mark_done(["p1", "p2", "p3"], batch=0)
    assert ck.remove(["p2", "p3"]) == 2     # drop the lost-write entries
    assert ck.done_post_ids() == {"p1"}
    assert ck.remove([]) == 0


def test_clear(tmp_path: Path) -> None:
    ck = L5IngestCheckpoint(tmp_path / "store.db", source_key="reddit_x")
    ck.mark_done(["p1", "p2"], batch=0)
    ck.clear()
    assert ck.count() == 0
