"""Tests for `src.extraction.pass2_labels.Pass2LabelsBuilder`."""

from __future__ import annotations

from datetime import UTC, datetime

from src.extraction.pass2_labels import Pass2LabelsBuilder
from src.ingestion.adapters.l5_reddit import L5RedditResult, RedditPost
from src.ingestion.adapters.l5_sdn import L5SDNResult, SDNPost, SDNThread


def _utc(year: int, month: int = 1, day: int = 1) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


def _reddit_post(pid: str = "abc", flair: str | None = None) -> RedditPost:
    return RedditPost(
        post_id=f"reddit_post:{pid}", raw_id=pid, subreddit="DentalSchool",
        author_user_id=None, raw_author=None,
        title=f"Title {pid}", selftext="",
        created_utc=_utc(2020, 1, 1),
        score=None, ups=None, downs=None, num_comments=None,
        link_flair_text=flair, permalink=None, url=None, over_18=False,
    )


def _sdn_post(pid: str, category: str = "Pre-Dental") -> SDNPost:
    return SDNPost(
        post_id=f"sdn_post:1:{pid}", raw_post_id=pid, thread_id="sdn_thread:1",
        thread_url="u", thread_title="X", category=category,
        page_number=1, author_user_id=None, raw_author=None,
        body="hi", created_utc=_utc(2020, 1, 1),
        is_thread_root=False,
    )


def test_reddit_flair_promotes_to_topic_node() -> None:
    result = L5RedditResult(
        subreddit="DentalSchool",
        posts=[_reddit_post(pid="a", flair="Acceptance")],
        comments=[], users=[],
    )

    out = Pass2LabelsBuilder().build_reddit(result, ingest_time=_utc(2026, 5, 21))

    topics = [n for n in out.nodes if n.label == "Topic"]
    assert len(topics) == 1
    assert topics[0].id == "topic:acceptance"
    assert topics[0].properties["label"] == "Acceptance"

    assert len(out.edges) == 1
    assert out.edges[0].label == "REFERENCES_TOPIC"
    assert out.edges[0].from_id == "reddit_post:a"
    assert out.edges[0].to_id == "topic:acceptance"


def test_reddit_posts_without_flair_emit_no_topic_edge() -> None:
    result = L5RedditResult(
        subreddit="DentalSchool",
        posts=[_reddit_post(pid="a"), _reddit_post(pid="b", flair="")],
        comments=[], users=[],
    )

    out = Pass2LabelsBuilder().build_reddit(result, ingest_time=_utc(2026, 5, 21))

    assert out.nodes == []
    assert out.edges == []


def test_reddit_dedupes_topic_nodes_across_posts() -> None:
    result = L5RedditResult(
        subreddit="DentalSchool",
        posts=[
            _reddit_post(pid="a", flair="Acceptance"),
            _reddit_post(pid="b", flair="Acceptance"),
            _reddit_post(pid="c", flair="DAT"),
        ],
        comments=[], users=[],
    )

    out = Pass2LabelsBuilder().build_reddit(result, ingest_time=_utc(2026, 5, 21))

    topic_ids = {n.id for n in out.nodes}
    assert topic_ids == {"topic:acceptance", "topic:dat"}
    assert len(out.edges) == 3


def test_sdn_category_promotes_to_topic_node() -> None:
    thread = SDNThread(
        thread_id="sdn_thread:1", raw_thread_id="1", title="X",
        category="Pre-Dental", url="u", reply_count=None,
        view_count=None, root_post_id=None,
    )
    result = L5SDNResult(
        posts=[_sdn_post("a", category="Pre-Dental")],
        users=[], threads=[thread],
    )

    out = Pass2LabelsBuilder().build_sdn(result, ingest_time=_utc(2026, 5, 21))

    topics = [n for n in out.nodes if n.label == "Topic"]
    assert len(topics) == 1
    assert topics[0].id == "topic:pre_dental"
    assert out.edges[0].label == "REFERENCES_TOPIC"


def test_reddit_topic_node_carries_source_marker() -> None:
    result = L5RedditResult(
        subreddit="DentalSchool",
        posts=[_reddit_post(pid="a", flair="DAT prep")],
        comments=[], users=[],
    )

    out = Pass2LabelsBuilder().build_reddit(result, ingest_time=_utc(2026, 5, 21))

    assert out.nodes[0].properties["source"] == "reddit_flair"


def test_sdn_topic_node_carries_category_source_marker() -> None:
    thread = SDNThread(
        thread_id="sdn_thread:1", raw_thread_id="1", title="X",
        category="Pre-Dental", url="u", reply_count=None,
        view_count=None, root_post_id=None,
    )
    result = L5SDNResult(
        posts=[_sdn_post("a", category="Pre-Dental")],
        users=[], threads=[thread],
    )

    out = Pass2LabelsBuilder().build_sdn(result, ingest_time=_utc(2026, 5, 21))

    assert out.nodes[0].properties["source"] == "sdn_category"


def test_edge_carries_bitemporal_tuple() -> None:
    result = L5RedditResult(
        subreddit="DentalSchool",
        posts=[_reddit_post(pid="a", flair="DAT")],
        comments=[], users=[],
    )

    out = Pass2LabelsBuilder().build_reddit(result, ingest_time=_utc(2026, 5, 21))

    e = out.edges[0]
    assert e.t_valid_from == _utc(2020, 1, 1)
    assert e.t_ingest_from == _utc(2026, 5, 21)
    assert e.source_tier == "L5"


def test_edge_references_include_flair_or_category_text() -> None:
    reddit = L5RedditResult(
        subreddit="DentalSchool",
        posts=[_reddit_post(pid="a", flair="DAT")],
        comments=[], users=[],
    )
    out = Pass2LabelsBuilder().build_reddit(reddit, ingest_time=_utc(2026, 5, 21))
    assert "flair:DAT" in out.edges[0].references
    assert "reddit_post:a" in out.edges[0].references
