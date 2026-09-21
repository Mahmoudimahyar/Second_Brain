"""Tests for `src.extraction.pass1_structural.Pass1StructuralBuilder`."""

from __future__ import annotations

from datetime import UTC, datetime

from src.extraction.pass1_structural import Pass1StructuralBuilder, StructuralOutput
from src.ingestion.adapters.l1_excel import (
    L1Alias,
    L1IngestResult,
    L1School,
    L1SchoolYearMetric,
)
from src.ingestion.adapters.l5_reddit import (
    L5RedditResult,
    RedditComment,
    RedditPost,
    RedditUser,
)
from src.ingestion.adapters.l5_sdn import (
    L5SDNResult,
    SDNPost,
    SDNThread,
    SDNUser,
)


def _utc(year: int, month: int = 1, day: int = 1) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


def _ingest() -> datetime:
    return _utc(2026, 5, 21)


def _reddit_post(
    pid: str = "abc", author: str | None = "reddit:DentalSchool:alice",
) -> RedditPost:
    return RedditPost(
        post_id=f"reddit_post:{pid}", raw_id=pid, subreddit="DentalSchool",
        author_user_id=author, raw_author="alice" if author else None,
        title=f"Title {pid}", selftext="body",
        created_utc=_utc(2020, 1, 1),
        score=10, ups=10, downs=0, num_comments=3,
        link_flair_text=None, permalink=None, url=None, over_18=False,
    )


def _reddit_comment(
    cid: str = "c1", post_id: str = "reddit_post:abc",
    parent_id: str | None = None, author: str | None = "reddit:DentalSchool:bob",
) -> RedditComment:
    return RedditComment(
        comment_id=f"reddit_comment:{cid}", raw_id=cid, subreddit="DentalSchool",
        post_id=post_id, parent_id=parent_id or post_id,
        author_user_id=author, raw_author="bob" if author else None,
        body="comment body", created_utc=_utc(2020, 1, 2),
        score=2, ups=2, downs=0, controversiality=0,
    )


def _reddit_user(uid: str = "reddit:DentalSchool:alice") -> RedditUser:
    return RedditUser(
        user_id=uid, username=uid.rsplit(":", maxsplit=1)[-1],
        subreddit="DentalSchool", first_seen_utc=_utc(2020, 1, 1),
    )


def test_assemble_reddit_emits_subreddit_node() -> None:
    result = L5RedditResult(
        subreddit="DentalSchool", posts=[], comments=[], users=[],
    )
    out = Pass1StructuralBuilder().assemble_reddit(result, ingest_time=_ingest())

    sub = next(n for n in out.nodes if n.label == "Subreddit")
    assert sub.id == "subreddit:DentalSchool"
    assert sub.source_tier == "L5"


def test_assemble_reddit_post_emits_node_and_edges() -> None:
    result = L5RedditResult(
        subreddit="DentalSchool",
        posts=[_reddit_post()],
        comments=[],
        users=[_reddit_user()],
    )

    out = Pass1StructuralBuilder().assemble_reddit(result, ingest_time=_ingest())

    labels = {n.label for n in out.nodes}
    assert {"Subreddit", "User", "Post"} <= labels
    edge_labels = {e.label for e in out.edges}
    assert {"POSTED_IN_FORUM", "AUTHORED"} <= edge_labels


def test_assemble_reddit_skips_authored_edge_for_deleted_author() -> None:
    result = L5RedditResult(
        subreddit="DentalSchool",
        posts=[_reddit_post(author=None)],
        comments=[],
        users=[],
    )

    out = Pass1StructuralBuilder().assemble_reddit(result, ingest_time=_ingest())

    authored = [e for e in out.edges if e.label == "AUTHORED"]
    assert authored == []
    posted = [e for e in out.edges if e.label == "POSTED_IN_FORUM"]
    assert len(posted) == 1


def test_assemble_reddit_comment_emits_three_edges() -> None:
    result = L5RedditResult(
        subreddit="DentalSchool",
        posts=[_reddit_post()],
        comments=[_reddit_comment(cid="c1", parent_id="reddit_post:abc")],
        users=[_reddit_user(), _reddit_user("reddit:DentalSchool:bob")],
    )

    out = Pass1StructuralBuilder().assemble_reddit(result, ingest_time=_ingest())

    by_label: dict[str, list[str]] = {}
    for e in out.edges:
        by_label.setdefault(e.label, []).append(e.id)
    # For comment c1 we should see REPLIED_TO + BELONGS_TO_THREAD + AUTHORED
    assert any(eid.endswith("c1") for eid in by_label.get("REPLIED_TO", []))
    assert any(eid.endswith("c1") for eid in by_label.get("BELONGS_TO_THREAD", []))
    assert any(":c1" in eid for eid in by_label.get("AUTHORED", []))


def test_assemble_reddit_carries_bitemporal_tuple() -> None:
    result = L5RedditResult(
        subreddit="DentalSchool",
        posts=[_reddit_post()],
        comments=[],
        users=[_reddit_user()],
    )
    ingest = _ingest()

    out = Pass1StructuralBuilder().assemble_reddit(result, ingest_time=ingest)

    edge = next(e for e in out.edges if e.label == "AUTHORED")
    assert edge.t_valid_from == _utc(2020, 1, 1)
    assert edge.t_ingest_from == ingest
    assert edge.source_tier == "L5"
    assert edge.rank == "normal"
    assert edge.references == ["reddit_post:abc"]


def test_assemble_sdn_emits_category_thread_post_nodes() -> None:
    thread = SDNThread(
        thread_id="sdn_thread:1", raw_thread_id="1", title="X",
        category="Pre-Dental", url="u", reply_count=None,
        view_count=None, root_post_id="sdn_post:1:a",
    )
    post_root = SDNPost(
        post_id="sdn_post:1:a", raw_post_id="a", thread_id="sdn_thread:1",
        thread_url="u", thread_title="X", category="Pre-Dental", page_number=1,
        author_user_id="sdn:alice", raw_author="alice", body="root",
        created_utc=_utc(2020, 1, 1), is_thread_root=True,
    )
    post_reply = SDNPost(
        post_id="sdn_post:1:b", raw_post_id="b", thread_id="sdn_thread:1",
        thread_url="u", thread_title="X", category="Pre-Dental", page_number=1,
        author_user_id="sdn:bob", raw_author="bob", body="reply",
        created_utc=_utc(2020, 1, 2), is_thread_root=False,
    )
    users = [
        SDNUser(user_id="sdn:alice", username="alice", first_seen_utc=_utc(2020, 1, 1)),
        SDNUser(user_id="sdn:bob", username="bob", first_seen_utc=_utc(2020, 1, 2)),
    ]
    sdn = L5SDNResult(posts=[post_root, post_reply], users=users, threads=[thread])

    out = Pass1StructuralBuilder().assemble_sdn(sdn, ingest_time=_ingest())

    labels = {n.label for n in out.nodes}
    assert {"SDNCategory", "SDNThread", "User", "Post"} <= labels
    edges_by_label = {e.label for e in out.edges}
    assert {"BELONGS_TO_THREAD", "POSTED_IN_FORUM", "AUTHORED", "REPLIED_TO"} <= edges_by_label

    replied = [e for e in out.edges if e.label == "REPLIED_TO"]
    assert len(replied) == 1
    assert replied[0].from_id == "sdn_post:1:b"
    assert replied[0].to_id == "sdn_post:1:a"


def test_assemble_sdn_does_not_emit_replied_to_for_root_post() -> None:
    thread = SDNThread(
        thread_id="sdn_thread:1", raw_thread_id="1", title="X",
        category="Pre-Dental", url="u", reply_count=None,
        view_count=None, root_post_id="sdn_post:1:a",
    )
    root = SDNPost(
        post_id="sdn_post:1:a", raw_post_id="a", thread_id="sdn_thread:1",
        thread_url="u", thread_title="X", category="Pre-Dental", page_number=1,
        author_user_id=None, raw_author=None, body="hi",
        created_utc=_utc(2020, 1, 1), is_thread_root=True,
    )
    out = Pass1StructuralBuilder().assemble_sdn(
        L5SDNResult(posts=[root], users=[], threads=[thread]),
        ingest_time=_ingest(),
    )
    assert [e for e in out.edges if e.label == "REPLIED_TO"] == []


def test_assemble_l1_emits_school_metric_alias_nodes_and_edges() -> None:
    school = L1School(
        canonical_id="school:nyu", canonical_name="NYU College of Dentistry",
        city="New York", state="NY", source_row="Tab1!A5",
    )
    metric = L1SchoolYearMetric(
        metric_id="metric:school_nyu:tuition:2024-25",
        canonical_school_id="school:nyu",
        cycle_year="2024-25", metric_name="Tuition Resident",
        metric_value=94108.0, unit=None, source_row="Tab1!D5",
        t_valid_from=_utc(2024, 9, 1), t_valid_to=_utc(2025, 8, 31),
    )
    alias = L1Alias(
        alias_text="NYU College of Dentistry",
        canonical_id="school:nyu",
        alias_source="manual", confidence=1.0,
    )
    result = L1IngestResult(
        cycle_year="2024-25",
        schools=[school], metrics=[metric], aliases=[alias],
    )

    out = Pass1StructuralBuilder().assemble_l1(
        result, source_dump_id="dump:abc", ingest_time=_ingest(),
    )

    labels = {n.label for n in out.nodes}
    assert {"School", "Metric", "CycleYear"} <= labels

    edge_labels = {e.label for e in out.edges}
    assert {"SCHOOL_HAS_METRIC", "HAS_ALIAS"} <= edge_labels

    school_has_metric = next(e for e in out.edges if e.label == "SCHOOL_HAS_METRIC")
    assert school_has_metric.source_tier == "L1"
    assert school_has_metric.rank == "preferred"
    assert school_has_metric.t_valid_from == _utc(2024, 9, 1)
    assert school_has_metric.qualifiers["cycle"] == "2024-25"


def test_assemble_l1_uses_preferred_rank() -> None:
    school = L1School(
        canonical_id="school:harvard",
        canonical_name="Harvard", city=None, state=None, source_row="x",
    )
    result = L1IngestResult(
        cycle_year="2024-25", schools=[school], metrics=[],
        aliases=[L1Alias(
            alias_text="Harvard", canonical_id="school:harvard",
            alias_source="manual", confidence=1.0,
        )],
    )

    out = Pass1StructuralBuilder().assemble_l1(
        result, source_dump_id="dump:y", ingest_time=_ingest(),
    )

    has_alias = next(e for e in out.edges if e.label == "HAS_ALIAS")
    assert has_alias.rank == "preferred"
    assert has_alias.source_tier == "L1"


def test_structural_output_is_pure() -> None:
    """The builder doesn't touch a graph store — output is a plain list pair."""

    result = L5RedditResult(
        subreddit="DentalSchool",
        posts=[_reddit_post()], comments=[], users=[_reddit_user()],
    )
    out = Pass1StructuralBuilder().assemble_reddit(result, ingest_time=_ingest())
    assert isinstance(out, StructuralOutput)
    assert isinstance(out.nodes, list)
    assert isinstance(out.edges, list)
