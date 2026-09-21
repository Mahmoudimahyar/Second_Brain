"""Round-trip tests: V1 adapters wrapped as `LocalFileDataSource` produce
canonical records bit-identical to V1's direct `parse()` call (FR-1.5a-1.2).
"""

from __future__ import annotations

from pathlib import Path

import orjson
import pytest

from src.ingestion.adapters.l5_reddit import L5RedditAdapter
from src.ingestion.sources.base import (
    CanonicalRecord,
    LocalFileConfig,
    SourceManifest,
)
from src.ingestion.sources.local_file import LocalFileDataSource
from src.shared.errors import ErrorCode, StructuredError


def _post(*, rid: str, title: str = "post", body: str = "",
          subreddit: str = "DentalSchool", score: int = 5,
          created_utc: int = 1_700_000_000) -> dict:
    return {
        "id": rid,
        "name": f"t3_{rid}",
        "author": "alice",
        "created_utc": created_utc,
        "title": title,
        "selftext": body,
        "subreddit": subreddit,
        "subreddit_id": "t5_xxx",
        "score": score,
        "ups": score,
        "downs": 0,
        "num_comments": 0,
        "link_flair_text": None,
        "permalink": f"/r/{subreddit}/comments/{rid}/_",
        "url": "https://example.org/",
        "over_18": False,
    }


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("wb") as f:
        for r in records:
            f.write(orjson.dumps(r))
            f.write(b"\n")


@pytest.fixture
def reddit_posts_file(tmp_path: Path) -> Path:
    fixture = tmp_path / "DentalSchool_posts.jsonl"
    _write_jsonl(fixture, [
        _post(rid="aaa1", title="Personal statement help"),
        _post(rid="aaa2", title="Interview at NYU"),
        _post(rid="aaa3", title="DAT score 23 chances"),
    ])
    return fixture


def test_local_file_round_trip_reddit(reddit_posts_file: Path) -> None:
    """Wrapping L5RedditAdapter as LocalFileDataSource yields bit-identical
    canonical records to the direct parse() call. Lifecycle is round-trippable.
    """
    manifest = SourceManifest(
        source_id="ds:local_file:test_reddit",
        engine="local_file",
        display_name="Test Reddit",
        config=LocalFileConfig(
            adapter="l5_reddit",
            paths=[str(reddit_posts_file)],
        ),
        tier="L5",
        credential_ref=None,
        notes=None,
    )

    direct = L5RedditAdapter().parse(reddit_posts_file)

    ds = LocalFileDataSource(manifest)
    with ds:
        snapshot = ds.discover_schema()
        records: list[CanonicalRecord] = list(ds.pull_delta(cursor=None))

    assert snapshot.source_id == "ds:local_file:test_reddit"
    assert snapshot.tables, "expected at least one table descriptor"
    assert {t.name for t in snapshot.tables} == {"post", "comment", "user"}

    posts = [r.payload for r in records if r.table_or_label == "post"]
    users = [r.payload for r in records if r.table_or_label == "user"]
    comments = [r.payload for r in records if r.table_or_label == "comment"]

    assert posts == list(direct.posts)
    assert users == list(direct.users)
    assert comments == list(direct.comments) == []


def test_pull_delta_idempotent_on_unchanged_files(
    reddit_posts_file: Path,
) -> None:
    """FR-1.5a-6.2 carried into Phase 1: identical file content + identical
    cursor → no-op second pull.
    """
    manifest = SourceManifest(
        source_id="ds:local_file:test_reddit",
        engine="local_file",
        display_name="Test Reddit",
        config=LocalFileConfig(
            adapter="l5_reddit",
            paths=[str(reddit_posts_file)],
        ),
        tier="L5",
        credential_ref=None,
        notes=None,
    )
    ds = LocalFileDataSource(manifest)
    with ds:
        first = list(ds.pull_delta(cursor=None))
        new_cursor = ds.advance_cursor()
        second = list(ds.pull_delta(cursor=new_cursor))

    assert first  # got records
    assert second == []  # idempotent
    assert new_cursor is not None
    assert new_cursor.cursor_value


def test_sample_rows_returns_subset(reddit_posts_file: Path) -> None:
    manifest = SourceManifest(
        source_id="ds:local_file:test_reddit",
        engine="local_file",
        display_name="Test Reddit",
        config=LocalFileConfig(
            adapter="l5_reddit",
            paths=[str(reddit_posts_file)],
        ),
        tier="L5",
        credential_ref=None,
        notes=None,
    )
    ds = LocalFileDataSource(manifest)
    with ds:
        rows = ds.sample_rows("post", n=2)
    assert len(rows) == 2
    assert all(isinstance(r, dict) for r in rows)
    assert "post_id" in rows[0]


def test_lifecycle_idempotent_open_close(reddit_posts_file: Path) -> None:
    """Repeated open()/close() cycles must not leak file handles."""
    manifest = SourceManifest(
        source_id="ds:local_file:test_reddit",
        engine="local_file",
        display_name="Test Reddit",
        config=LocalFileConfig(
            adapter="l5_reddit",
            paths=[str(reddit_posts_file)],
        ),
        tier="L5",
        credential_ref=None,
        notes=None,
    )
    ds = LocalFileDataSource(manifest)
    for _ in range(5):
        ds.open()
        assert ds.is_open()
        ds.close()
        assert not ds.is_open()


def test_missing_payload_raises_structured_error(tmp_path: Path) -> None:
    manifest = SourceManifest(
        source_id="ds:local_file:missing",
        engine="local_file",
        display_name="Missing",
        config=LocalFileConfig(
            adapter="l5_reddit",
            paths=[str(tmp_path / "nonexistent.jsonl")],
        ),
        tier="L5",
        credential_ref=None,
        notes=None,
    )
    ds = LocalFileDataSource(manifest)
    with pytest.raises(StructuredError) as excinfo:
        ds.open()
    assert excinfo.value.error_code == ErrorCode.INGESTION_PAYLOAD_MISSING


@pytest.mark.parametrize("adapter_kind,fixture_files", [
    ("l5_reddit", ["DentalSchool_posts.jsonl"]),
])
def test_each_v1_adapter_wrappable(
    tmp_path: Path,
    adapter_kind: str,
    fixture_files: list[str],
) -> None:
    """Smoke: each V1 adapter kind successfully wraps in LocalFileDataSource.

    Phase 1 ships the Reddit wrapping (used by primary AC-1 test). Other
    adapters (l1_excel, l1_pdf, l2_html, l5_sdn) gain wrapping coverage via
    their own dedicated tests in Phase 1.x. This parametrize anchors the
    contract; new adapters slot in here.
    """
    file_path = tmp_path / fixture_files[0]
    _write_jsonl(file_path, [_post(rid="x1")])
    manifest = SourceManifest(
        source_id=f"ds:local_file:{adapter_kind}",
        engine="local_file",
        display_name=f"Test {adapter_kind}",
        config=LocalFileConfig(adapter=adapter_kind, paths=[str(file_path)]),
        tier="L5",
        credential_ref=None,
        notes=None,
    )
    ds = LocalFileDataSource(manifest)
    with ds:
        records = list(ds.pull_delta(cursor=None))
    assert records  # non-empty
