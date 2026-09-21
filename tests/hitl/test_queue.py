"""Tests for `src.hitl.queue.HITLQueue` (FR-10)."""

from __future__ import annotations

from pathlib import Path

from src.hitl import Decision, HITLQueue, ItemStatus


def _queue(tmp_path: Path) -> HITLQueue:
    return HITLQueue(sqlite_path=tmp_path / "hitl.db")


def test_enqueue_returns_unique_item_id(tmp_path: Path) -> None:
    q = _queue(tmp_path)
    a = q.enqueue(item_type="alias_match", payload={"alias": "UPenn"})
    b = q.enqueue(item_type="alias_match", payload={"alias": "NYU"})
    assert a != b
    assert a.startswith("hitl:")


def test_pull_returns_pending_item_and_marks_claimed(tmp_path: Path) -> None:
    q = _queue(tmp_path)
    q.enqueue(item_type="conflict", payload={"a": 1})

    item = q.pull(reviewer="mahyar")

    assert item is not None
    assert item.status == ItemStatus.CLAIMED
    assert item.claimed_by == "mahyar"
    assert item.claimed_at is not None


def test_pull_returns_none_when_queue_empty(tmp_path: Path) -> None:
    q = _queue(tmp_path)
    assert q.pull() is None


def test_pull_returns_items_in_fifo_order(tmp_path: Path) -> None:
    q = _queue(tmp_path)
    q.enqueue(item_type="t", payload={"i": 1})
    q.enqueue(item_type="t", payload={"i": 2})

    first = q.pull()
    second = q.pull()
    assert first is not None and second is not None
    assert first.payload["i"] == 1
    assert second.payload["i"] == 2


def test_commit_finalizes_item(tmp_path: Path) -> None:
    q = _queue(tmp_path)
    iid = q.enqueue(item_type="alias_match", payload={"x": 1})
    q.pull()

    after = q.commit(iid, Decision(verdict="accept", notes="looks good"))

    assert after is not None
    assert after.status == ItemStatus.COMMITTED
    assert after.decision is not None
    assert after.decision.verdict == "accept"
    assert after.committed_at is not None


def test_commit_can_escalate(tmp_path: Path) -> None:
    q = _queue(tmp_path)
    iid = q.enqueue(item_type="conflict", payload={"x": 1})
    q.pull()

    after = q.commit(iid, Decision(verdict="needs_l2_source"), escalate=True)
    assert after is not None
    assert after.status == ItemStatus.ESCALATED


def test_commit_is_idempotent_on_committed_item(tmp_path: Path) -> None:
    q = _queue(tmp_path)
    iid = q.enqueue(item_type="t", payload={})
    q.pull()
    q.commit(iid, Decision(verdict="accept"))
    again = q.commit(iid, Decision(verdict="reject"))
    assert again is not None
    assert again.decision is not None
    assert again.decision.verdict == "accept"


def test_list_items_filters_by_status(tmp_path: Path) -> None:
    q = _queue(tmp_path)
    for i in range(3):
        q.enqueue(item_type="t", payload={"i": i})
    q.pull()  # one is now claimed

    pending = q.list_items(status=ItemStatus.PENDING)
    claimed = q.list_items(status=ItemStatus.CLAIMED)

    assert len(pending) == 2
    assert len(claimed) == 1


def test_get_returns_none_for_missing_id(tmp_path: Path) -> None:
    assert _queue(tmp_path).get("hitl:none") is None
