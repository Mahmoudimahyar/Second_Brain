"""Tests for the KI-006 keyword filter in `L5RedditAdapter.parse`."""

from __future__ import annotations

from pathlib import Path

import orjson

from src.ingestion.adapters.l5_reddit import (
    DEFAULT_ADMISSIONS_KEYWORDS,
    L5RedditAdapter,
)


def _post(rid: str, title: str, selftext: str = "", *,
          author: str = "alice", subreddit: str = "dentistry") -> dict:
    return {
        "id": rid, "name": f"t3_{rid}", "author": author,
        "created_utc": 1306446997,
        "title": title, "selftext": selftext,
        "subreddit": subreddit, "subreddit_id": "t5_1",
        "score": 1, "ups": 1, "downs": 0, "num_comments": 0,
        "link_flair_text": None, "permalink": None, "url": None,
        "over_18": False,
    }


def _comment(cid: str, link_id: str, body: str = "comment body",
             author: str = "bob") -> dict:
    return {
        "id": cid, "name": f"t1_{cid}", "author": author,
        "body": body, "created_utc": 1316788978,
        "link_id": link_id, "parent_id": link_id,
        "subreddit": "dentistry", "subreddit_id": "t5_1",
        "score": 1, "ups": 1, "downs": 0, "controversiality": 0,
    }


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("wb") as f:
        for r in records:
            f.write(orjson.dumps(r))
            f.write(b"\n")


def test_no_filter_keeps_all_posts(tmp_path: Path) -> None:
    posts_path = tmp_path / "r_dentistry_posts.jsonl"
    _write_jsonl(posts_path, [
        _post("a", "What toothpaste should I use?"),
        _post("b", "DAT prep advice please"),
    ])

    result = L5RedditAdapter().parse(posts_path)
    assert {p.raw_id for p in result.posts} == {"a", "b"}


def test_keyword_filter_keeps_only_matching_posts(tmp_path: Path) -> None:
    posts_path = tmp_path / "r_dentistry_posts.jsonl"
    _write_jsonl(posts_path, [
        _post("relevant1", "DAT prep advice for next cycle"),
        _post("relevant2", "Looking at predental requirements"),
        _post("irrelevant1", "What toothpaste should I use?"),
        _post("irrelevant2", "Best floss brand?"),
    ])

    result = L5RedditAdapter().parse(
        posts_path,
        keyword_filter=list(DEFAULT_ADMISSIONS_KEYWORDS),
    )

    kept_ids = {p.raw_id for p in result.posts}
    assert "relevant1" in kept_ids
    assert "relevant2" in kept_ids
    assert "irrelevant1" not in kept_ids
    assert "irrelevant2" not in kept_ids


def test_keyword_filter_is_case_insensitive(tmp_path: Path) -> None:
    posts_path = tmp_path / "r_dentistry_posts.jsonl"
    _write_jsonl(posts_path, [
        _post("a", "DENTAL SCHOOL acceptance just came!"),
    ])

    result = L5RedditAdapter().parse(
        posts_path, keyword_filter=["dental school"],
    )
    assert len(result.posts) == 1


def test_keyword_filter_checks_body_not_just_title(tmp_path: Path) -> None:
    posts_path = tmp_path / "r_dentistry_posts.jsonl"
    _write_jsonl(posts_path, [
        _post("a", "Random title",
              "But the body mentions DAT prep questions"),
    ])

    result = L5RedditAdapter().parse(
        posts_path, keyword_filter=["DAT"],
    )
    assert len(result.posts) == 1


def test_comments_dropped_when_root_post_filtered(tmp_path: Path) -> None:
    posts_path = tmp_path / "r_dentistry_posts.jsonl"
    comments_path = tmp_path / "r_dentistry_comments.jsonl"
    _write_jsonl(posts_path, [
        _post("kept", "Need DAT prep tips"),
        _post("dropped", "Best floss brand?"),
    ])
    _write_jsonl(comments_path, [
        _comment("c1", "t3_kept"),
        _comment("c2", "t3_dropped"),
    ])

    result = L5RedditAdapter().parse(
        posts_path, comments_path,
        keyword_filter=list(DEFAULT_ADMISSIONS_KEYWORDS),
    )

    kept_post_ids = {p.raw_id for p in result.posts}
    assert kept_post_ids == {"kept"}
    # Comments attached to dropped posts are also gone.
    comment_post_ids = {c.post_id for c in result.comments}
    assert comment_post_ids == {"reddit_post:kept"}


def test_empty_keyword_list_keeps_all(tmp_path: Path) -> None:
    posts_path = tmp_path / "r_dentistry_posts.jsonl"
    _write_jsonl(posts_path, [_post("a", "Random title")])

    # Empty filter list = "no filter"
    result = L5RedditAdapter().parse(posts_path, keyword_filter=[])
    assert len(result.posts) == 1


def test_default_keywords_cover_common_dental_school_terms() -> None:
    """Sanity: the default filter list includes core admissions vocabulary."""

    kw = set(DEFAULT_ADMISSIONS_KEYWORDS)
    assert "DAT" in kw
    assert "interview" in kw
    assert "acceptance" in kw
    assert "applicant" in kw
    assert "AADSAS" in kw
