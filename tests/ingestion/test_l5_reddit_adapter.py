"""Tests for `src.ingestion.adapters.l5_reddit.L5RedditAdapter` (FR-1.3, FR-1.5)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from pathlib import Path

import orjson
import pytest

from src.ingestion.adapters.l5_reddit import (
    L5RedditAdapter,
    L5RedditResult,
    RedditComment,
    RedditPost,
    RedditUser,
)


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("wb") as f:
        for r in records:
            f.write(orjson.dumps(r))
            f.write(b"\n")


def _post_record(
    *,
    rid: str = "hl06x",
    author: str = "ViP_Suite",
    created_utc: int = 1306446997,
    title: str = "Hello world",
    selftext: str = "post body",
    subreddit: str = "DentalSchool",
    link_flair_text: str | None = None,
    score: int = 5,
) -> dict:
    return {
        "id": rid,
        "name": f"t3_{rid}",
        "author": author,
        "created_utc": created_utc,
        "title": title,
        "selftext": selftext,
        "subreddit": subreddit,
        "subreddit_id": "t5_2siqo",
        "score": score,
        "ups": score,
        "downs": 0,
        "num_comments": 0,
        "link_flair_text": link_flair_text,
        "permalink": f"/r/{subreddit}/comments/{rid}/_",
        "url": "https://example.org/",
        "over_18": False,
    }


def _comment_record(
    *,
    cid: str = "c2m0mgt",
    author: str = "ayton",
    link_id: str = "t3_hl06x",
    parent_id: str | None = None,
    body: str = "I think this is interesting",
    created_utc: int = 1316788978,
    subreddit: str = "DentalSchool",
) -> dict:
    return {
        "id": cid,
        "name": f"t1_{cid}",
        "author": author,
        "body": body,
        "created_utc": created_utc,
        "link_id": link_id,
        "parent_id": parent_id or link_id,
        "subreddit": subreddit,
        "subreddit_id": "t5_2siqo",
        "score": 1,
        "ups": 1,
        "downs": 0,
        "controversiality": 0,
    }


def test_parse_returns_result_with_posts_and_users(tmp_path: Path) -> None:
    posts = tmp_path / "r_DentalSchool_posts.jsonl"
    _write_jsonl(posts, [_post_record(), _post_record(rid="abc", author="ada")])

    result = L5RedditAdapter().parse(posts)

    assert isinstance(result, L5RedditResult)
    assert result.subreddit == "DentalSchool"
    assert len(result.posts) == 2
    assert len(result.users) == 2


def test_parse_canonicalizes_post_id(tmp_path: Path) -> None:
    posts = tmp_path / "r_DentalSchool_posts.jsonl"
    _write_jsonl(posts, [_post_record(rid="abc123")])

    result = L5RedditAdapter().parse(posts)

    assert result.posts[0].post_id == "reddit_post:abc123"
    assert result.posts[0].raw_id == "abc123"


def test_parse_namespaces_author_per_subreddit(tmp_path: Path) -> None:
    posts = tmp_path / "r_DentalSchool_posts.jsonl"
    _write_jsonl(posts, [_post_record(author="alice")])

    result = L5RedditAdapter().parse(posts)

    assert result.posts[0].author_user_id == "reddit:DentalSchool:alice"
    assert result.users[0].user_id == "reddit:DentalSchool:alice"


def test_parse_handles_deleted_author(tmp_path: Path) -> None:
    posts = tmp_path / "r_DentalSchool_posts.jsonl"
    _write_jsonl(
        posts,
        [
            _post_record(rid="a", author="[deleted]"),
            _post_record(rid="b", author="[removed]"),
            _post_record(rid="c", author=""),
        ],
    )

    result = L5RedditAdapter().parse(posts)

    assert len(result.posts) == 3
    assert all(p.author_user_id is None for p in result.posts)
    assert result.users == []


def test_parse_converts_unix_epoch_to_utc(tmp_path: Path) -> None:
    posts = tmp_path / "r_DentalSchool_posts.jsonl"
    _write_jsonl(posts, [_post_record(created_utc=1306446997)])

    result = L5RedditAdapter().parse(posts)

    expected = datetime.fromtimestamp(1306446997, tz=UTC)
    assert result.posts[0].created_utc == expected
    assert result.posts[0].created_utc.tzinfo is UTC


def test_parse_reads_comments_and_links_to_post(tmp_path: Path) -> None:
    posts = tmp_path / "r_DentalSchool_posts.jsonl"
    comments = tmp_path / "r_DentalSchool_comments.jsonl"
    _write_jsonl(posts, [_post_record(rid="hl06x")])
    _write_jsonl(
        comments,
        [
            _comment_record(cid="c1", link_id="t3_hl06x"),
            _comment_record(cid="c2", link_id="t3_hl06x", parent_id="t1_c1"),
        ],
    )

    result = L5RedditAdapter().parse(posts, comments)

    assert len(result.comments) == 2
    assert result.comments[0].post_id == "reddit_post:hl06x"
    assert result.comments[0].parent_id == "reddit_post:hl06x"
    assert result.comments[1].post_id == "reddit_post:hl06x"
    assert result.comments[1].parent_id == "reddit_comment:c1"


def test_parse_skips_orphan_comments_without_link_id(tmp_path: Path) -> None:
    posts = tmp_path / "r_DentalSchool_posts.jsonl"
    comments = tmp_path / "r_DentalSchool_comments.jsonl"
    _write_jsonl(posts, [_post_record()])
    raw_orphan = _comment_record()
    raw_orphan.pop("link_id")
    _write_jsonl(comments, [raw_orphan])

    result = L5RedditAdapter().parse(posts, comments)

    assert result.comments == []


def test_parse_dedupes_users_across_posts_and_comments(tmp_path: Path) -> None:
    posts = tmp_path / "r_DentalSchool_posts.jsonl"
    comments = tmp_path / "r_DentalSchool_comments.jsonl"
    _write_jsonl(
        posts,
        [
            _post_record(rid="p1", author="alice", created_utc=1000),
            _post_record(rid="p2", author="alice", created_utc=2000),
            _post_record(rid="p3", author="bob", created_utc=1500),
        ],
    )
    _write_jsonl(
        comments,
        [_comment_record(cid="c1", author="alice", link_id="t3_p1", created_utc=500)],
    )

    result = L5RedditAdapter().parse(posts, comments)

    by_id = {u.user_id: u for u in result.users}
    assert set(by_id.keys()) == {
        "reddit:DentalSchool:alice",
        "reddit:DentalSchool:bob",
    }
    assert by_id["reddit:DentalSchool:alice"].first_seen_utc == datetime.fromtimestamp(
        500, tz=UTC,
    )
    assert by_id["reddit:DentalSchool:bob"].first_seen_utc == datetime.fromtimestamp(
        1500, tz=UTC,
    )


def test_parse_distinct_users_per_subreddit(tmp_path: Path) -> None:
    posts_a = tmp_path / "r_DentalSchool_posts.jsonl"
    posts_b = tmp_path / "r_predental_posts.jsonl"
    _write_jsonl(posts_a, [_post_record(author="alice", subreddit="DentalSchool")])
    _write_jsonl(posts_b, [_post_record(rid="other", author="alice", subreddit="predental")])

    result_a = L5RedditAdapter().parse(posts_a)
    result_b = L5RedditAdapter().parse(posts_b)

    assert result_a.users[0].user_id == "reddit:DentalSchool:alice"
    assert result_b.users[0].user_id == "reddit:predental:alice"
    assert result_a.users[0].user_id != result_b.users[0].user_id


def test_parse_preserves_link_flair_text(tmp_path: Path) -> None:
    posts = tmp_path / "r_DentalSchool_posts.jsonl"
    _write_jsonl(
        posts, [_post_record(link_flair_text="Acceptance"), _post_record(rid="b")],
    )

    result = L5RedditAdapter().parse(posts)

    flairs = [p.link_flair_text for p in result.posts]
    assert "Acceptance" in flairs
    assert None in flairs


def test_parse_skips_malformed_json_lines(tmp_path: Path) -> None:
    posts = tmp_path / "r_DentalSchool_posts.jsonl"
    with posts.open("wb") as f:
        f.write(orjson.dumps(_post_record(rid="ok1")))
        f.write(b"\n")
        f.write(b"{not-valid-json\n")
        f.write(orjson.dumps(_post_record(rid="ok2")))
        f.write(b"\n")
        f.write(b"\n")  # blank line

    result = L5RedditAdapter().parse(posts)

    assert {p.raw_id for p in result.posts} == {"ok1", "ok2"}


def test_parse_skips_records_without_id_or_timestamp(tmp_path: Path) -> None:
    posts = tmp_path / "r_DentalSchool_posts.jsonl"
    bad_no_id = _post_record()
    bad_no_id.pop("id")
    bad_no_ts = _post_record(rid="other")
    bad_no_ts.pop("created_utc")
    bad_no_ts.pop("created", None)
    _write_jsonl(posts, [bad_no_id, bad_no_ts, _post_record(rid="ok")])

    result = L5RedditAdapter().parse(posts)

    assert {p.raw_id for p in result.posts} == {"ok"}


def test_parse_raises_on_missing_posts_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        L5RedditAdapter().parse(tmp_path / "nope.jsonl")


def test_dataclasses_are_immutable() -> None:
    p = RedditPost(
        post_id="reddit_post:x", raw_id="x", subreddit="DentalSchool",
        author_user_id=None, raw_author=None, title="", selftext="",
        created_utc=datetime.now(UTC), score=None, ups=None, downs=None,
        num_comments=None, link_flair_text=None, permalink=None, url=None,
        over_18=False,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.title = "Other"  # type: ignore[misc]

    u = RedditUser(
        user_id="reddit:DentalSchool:x", username="x",
        subreddit="DentalSchool", first_seen_utc=datetime.now(UTC),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        u.username = "y"  # type: ignore[misc]

    c = RedditComment(
        comment_id="reddit_comment:x", raw_id="x", subreddit="DentalSchool",
        post_id="reddit_post:y", parent_id="reddit_post:y",
        author_user_id=None, raw_author=None, body="",
        created_utc=datetime.now(UTC), score=None, ups=None, downs=None,
        controversiality=None,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.body = "z"  # type: ignore[misc]


def test_canonicalize_thing_handles_known_prefixes() -> None:
    assert L5RedditAdapter._canonicalize_thing("t3_abc") == "reddit_post:abc"
    assert L5RedditAdapter._canonicalize_thing("t1_xyz") == "reddit_comment:xyz"
    # Unknown prefix: pass through unchanged (no false rewrites).
    assert L5RedditAdapter._canonicalize_thing("t5_2siqo") == "t5_2siqo"


def test_subreddit_inferred_from_filename(tmp_path: Path) -> None:
    p_a = tmp_path / "r_DentalSchool_posts.jsonl"
    p_b = tmp_path / "r_predental_posts.jsonl"
    p_c = tmp_path / "custom_dump_posts.jsonl"
    _write_jsonl(p_a, [_post_record()])
    _write_jsonl(p_b, [_post_record(subreddit="predental")])
    _write_jsonl(p_c, [_post_record(subreddit="custom_dump")])

    a = L5RedditAdapter().parse(p_a)
    b = L5RedditAdapter().parse(p_b)
    c = L5RedditAdapter().parse(p_c)

    assert a.subreddit == "DentalSchool"
    assert b.subreddit == "predental"
    assert c.subreddit == "custom_dump"
