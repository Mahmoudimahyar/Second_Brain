"""Tests for `src.ingestion.adapters.l5_sdn.L5SDNAdapter` (FR-1.4, FR-1.5)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from pathlib import Path

import orjson
import pytest

from src.ingestion.adapters.l5_sdn import (
    L5SDNAdapter,
    L5SDNResult,
    SDNThread,
    SDNUser,
)


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("wb") as f:
        for r in records:
            f.write(orjson.dumps(r))
            f.write(b"\n")


def _thread_meta(
    *, tid: str = "379553", title: str = "Kaplan DAT",
    category: str = "Pre-Dental", reply_count: int | None = 12,
) -> dict:
    return {
        "thread_id": tid,
        "thread_url": f"https://forums.studentdoctor.net/threads/x.{tid}/",
        "title": title,
        "category": category,
        "discovered_page": 1,
        "total_pages": None,
        "reply_count": reply_count,
        "view_count": None,
        "status": "completed",
    }


def _post_record(
    *, tid: str = "379553", pid: str = "4878628",
    author: str = "comiccards2007", ts_iso: str = "2007-03-12T13:31:23-0400",
    content: str = "Hi everyone, does anyone have the DAT conversion charts?",
    page: int = 1,
) -> dict:
    return {
        "thread_id": tid,
        "thread_url": f"https://forums.studentdoctor.net/threads/x.{tid}/",
        "post_id": pid,
        "page_number": page,
        "author": author,
        "timestamp_str": ts_iso,
        "timestamp_iso": ts_iso,
        "content_text": content,
    }


def _make_fixture(tmp_path: Path, threads: list[dict], posts_by_thread: dict[str, list[dict]]) -> tuple[Path, Path]:
    meta_path = tmp_path / "sdn_thread_metadata.jsonl"
    posts_dir = tmp_path / "posts"
    posts_dir.mkdir()
    _write_jsonl(meta_path, threads)
    for tid, records in posts_by_thread.items():
        _write_jsonl(posts_dir / f"thread_{tid}_posts.jsonl", records)
    return meta_path, posts_dir


def test_parse_returns_result_with_threads_and_posts(tmp_path: Path) -> None:
    meta, posts_dir = _make_fixture(
        tmp_path,
        [_thread_meta(tid="100", title="DAT prep")],
        {"100": [_post_record(tid="100", pid="1")]},
    )

    result = L5SDNAdapter().parse(meta, posts_dir)

    assert isinstance(result, L5SDNResult)
    assert len(result.threads) == 1
    assert len(result.posts) == 1


def test_parse_filters_by_category(tmp_path: Path) -> None:
    meta, posts_dir = _make_fixture(
        tmp_path,
        [
            _thread_meta(tid="1", category="Pre-Dental"),
            _thread_meta(tid="2", category="Dental"),
            _thread_meta(tid="3", category="Pre-Dental"),
        ],
        {
            "1": [_post_record(tid="1", pid="a")],
            "2": [_post_record(tid="2", pid="b")],
            "3": [_post_record(tid="3", pid="c")],
        },
    )

    result = L5SDNAdapter().parse(meta, posts_dir, category="Pre-Dental")

    assert len(result.threads) == 2
    assert {t.raw_thread_id for t in result.threads} == {"1", "3"}


def test_parse_disables_category_filter_when_none(tmp_path: Path) -> None:
    meta, posts_dir = _make_fixture(
        tmp_path,
        [
            _thread_meta(tid="1", category="Pre-Dental"),
            _thread_meta(tid="2", category="Dental"),
        ],
        {
            "1": [_post_record(tid="1", pid="a")],
            "2": [_post_record(tid="2", pid="b")],
        },
    )

    result = L5SDNAdapter().parse(meta, posts_dir, category=None)

    assert len(result.threads) == 2


def test_parse_respects_max_threads(tmp_path: Path) -> None:
    threads_meta = [_thread_meta(tid=str(i)) for i in range(5)]
    posts_per = {str(i): [_post_record(tid=str(i), pid=f"p{i}")] for i in range(5)}
    meta, posts_dir = _make_fixture(tmp_path, threads_meta, posts_per)

    result = L5SDNAdapter().parse(meta, posts_dir, max_threads=2)

    assert len(result.threads) == 2


def test_parse_canonicalizes_ids(tmp_path: Path) -> None:
    meta, posts_dir = _make_fixture(
        tmp_path,
        [_thread_meta(tid="999")],
        {"999": [_post_record(tid="999", pid="42", author="alice")]},
    )

    result = L5SDNAdapter().parse(meta, posts_dir)

    p = result.posts[0]
    assert p.post_id == "sdn_post:999:42"
    assert p.thread_id == "sdn_thread:999"
    assert p.author_user_id == "sdn:alice"


def test_parse_marks_first_post_chronologically_as_thread_root(tmp_path: Path) -> None:
    meta, posts_dir = _make_fixture(
        tmp_path,
        [_thread_meta(tid="500")],
        {
            "500": [
                _post_record(tid="500", pid="b", ts_iso="2020-06-15T10:00:00+00:00"),
                _post_record(tid="500", pid="a", ts_iso="2020-01-01T08:00:00+00:00"),
                _post_record(tid="500", pid="c", ts_iso="2021-02-01T12:00:00+00:00"),
            ],
        },
    )

    result = L5SDNAdapter().parse(meta, posts_dir)

    root_posts = [p for p in result.posts if p.is_thread_root]
    assert len(root_posts) == 1
    assert root_posts[0].raw_post_id == "a"

    thread = result.threads[0]
    assert thread.root_post_id == "sdn_post:500:a"


def test_parse_handles_iso_timestamps(tmp_path: Path) -> None:
    meta, posts_dir = _make_fixture(
        tmp_path,
        [_thread_meta(tid="1")],
        {"1": [_post_record(tid="1", pid="a", ts_iso="2024-05-21T15:30:45+00:00")]},
    )

    result = L5SDNAdapter().parse(meta, posts_dir)

    assert result.posts[0].created_utc == datetime(2024, 5, 21, 15, 30, 45, tzinfo=UTC)


def test_parse_dedupes_users_by_first_seen(tmp_path: Path) -> None:
    meta, posts_dir = _make_fixture(
        tmp_path,
        [_thread_meta(tid="1"), _thread_meta(tid="2")],
        {
            "1": [
                _post_record(tid="1", pid="a", author="alice",
                              ts_iso="2020-01-01T00:00:00+00:00"),
                _post_record(tid="1", pid="b", author="alice",
                              ts_iso="2021-01-01T00:00:00+00:00"),
            ],
            "2": [
                _post_record(tid="2", pid="c", author="alice",
                              ts_iso="2019-06-01T00:00:00+00:00"),
            ],
        },
    )

    result = L5SDNAdapter().parse(meta, posts_dir)

    assert len(result.users) == 1
    assert result.users[0].user_id == "sdn:alice"
    assert result.users[0].first_seen_utc == datetime(2019, 6, 1, tzinfo=UTC)


def test_parse_handles_deleted_authors(tmp_path: Path) -> None:
    meta, posts_dir = _make_fixture(
        tmp_path,
        [_thread_meta(tid="1")],
        {
            "1": [
                _post_record(tid="1", pid="a", author="[deleted]"),
                _post_record(tid="1", pid="b", author=""),
            ],
        },
    )

    result = L5SDNAdapter().parse(meta, posts_dir)

    assert all(p.author_user_id is None for p in result.posts)
    assert result.users == []


def test_parse_handles_missing_thread_posts_file(tmp_path: Path) -> None:
    """Thread declared in metadata but no per-thread posts file present."""

    meta, posts_dir = _make_fixture(
        tmp_path,
        [_thread_meta(tid="orphan")],
        {},  # no posts file written
    )

    result = L5SDNAdapter().parse(meta, posts_dir)

    assert len(result.threads) == 1
    assert result.threads[0].root_post_id is None
    assert result.posts == []


def test_parse_skips_records_without_timestamp_or_post_id(tmp_path: Path) -> None:
    no_ts = _post_record(tid="1", pid="bad")
    no_ts.pop("timestamp_iso")
    no_id = _post_record(tid="1", pid="ok2")
    no_id.pop("post_id")
    meta, posts_dir = _make_fixture(
        tmp_path,
        [_thread_meta(tid="1")],
        {"1": [no_ts, no_id, _post_record(tid="1", pid="ok1")]},
    )

    result = L5SDNAdapter().parse(meta, posts_dir)

    assert {p.raw_post_id for p in result.posts} == {"ok1"}


def test_parse_namespaces_authors_distinctly_from_reddit() -> None:
    # SDN authors are namespaced `sdn:<author>` so the same string from
    # Reddit (`reddit:<sub>:<author>`) produces a distinct user node.
    assert L5SDNAdapter._author_or_none("alice") == "alice"
    p = L5SDNAdapter._normalize_post(
        {
            "post_id": "1",
            "author": "alice",
            "timestamp_iso": "2024-01-01T00:00:00+00:00",
            "content_text": "hi",
            "page_number": 1,
        },
        category="Pre-Dental",
        thread_title="t",
        thread_url="u",
        raw_thread_id="999",
    )
    assert p is not None
    assert p.author_user_id == "sdn:alice"


def test_parse_raises_on_missing_metadata_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        L5SDNAdapter().parse(tmp_path / "nope.jsonl", tmp_path)


def test_parse_raises_on_missing_posts_dir(tmp_path: Path) -> None:
    meta = tmp_path / "sdn_thread_metadata.jsonl"
    _write_jsonl(meta, [_thread_meta()])
    with pytest.raises(FileNotFoundError):
        L5SDNAdapter().parse(meta, tmp_path / "no_dir")


def test_dataclasses_are_immutable() -> None:
    t = SDNThread(
        thread_id="sdn_thread:1", raw_thread_id="1", title="t",
        category="Pre-Dental", url="u", reply_count=None, view_count=None,
        root_post_id=None,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.title = "x"  # type: ignore[misc]

    u = SDNUser(
        user_id="sdn:a", username="a", first_seen_utc=datetime.now(UTC),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        u.username = "z"  # type: ignore[misc]
