"""PV-1: provenance layer — deterministic stat ids, counted distributions with
retained source-id sets, LRU eviction, and clickable-URL reconstruction."""

from __future__ import annotations

from src.retrieval.dossier import _full_url
from src.retrieval.provenance import (
    ProvenanceStore, build_distribution, make_stat_id,
)


def test_make_stat_id_deterministic():
    assert make_stat_id("a", "b") == make_stat_id("a", "b")
    assert make_stat_id("a", "b") != make_stat_id("a", "c")
    assert make_stat_id("nyu", "positive").startswith("stat:")


def test_build_distribution_counts_store_and_order():
    s = ProvenanceStore()
    d = build_distribution(
        s, prefix="nyu:sent",
        buckets={"positive": ["c1", "c2", "c3"], "negative": ["c4"]},
        source_kind="reddit_comment", method="m")
    assert [x.label for x in d] == ["positive", "negative"]   # sorted by numerator desc
    pos = d[0]
    assert pos.numerator == 3 and pos.denominator == 4 and abs(pos.value - 0.75) < 1e-9
    # the FULL id set is retained (not just the sample) and drill-down points at it
    assert s.get(pos.stat_id)["ids"] == ["c1", "c2", "c3"]
    assert pos.to_dict()["drill_down"].endswith(pos.stat_id)
    assert pos.to_dict()["sample_ids"] == ["c1", "c2", "c3"]


def test_build_distribution_empty():
    s = ProvenanceStore()
    assert build_distribution(s, prefix="x", buckets={}, source_kind="forum", method="m") == []


def test_store_lru_eviction():
    s = ProvenanceStore(cap=2)
    for k in ("a", "b", "c"):
        s.record(k, [k], source_kind="k", method="m", label=k)
    assert s.get("a") is None        # oldest evicted
    assert s.get("c") is not None    # newest kept


def test_full_url_reddit_post_relative():
    assert _full_url("reddit_post:1abc", "/r/x/comments/1abc/t/", "reddit_post:1abc", {}) \
        == "https://www.reddit.com/r/x/comments/1abc/t/"


def test_full_url_reddit_comment_rebuilt_from_parent():
    pm = {"reddit_post:1abc": "/r/x/comments/1abc/t/"}
    assert _full_url("reddit_comment:xyz", "", "reddit_post:1abc", pm) \
        == "https://www.reddit.com/r/x/comments/1abc/t/xyz/"


def test_full_url_sdn_absolute_kept():
    u = "https://forums.studentdoctor.net/threads/x.1/"
    assert _full_url("sdn_post:1:2", u, "sdn_thread:1", {}) == u


def test_full_url_missing_parent_yields_empty():
    assert _full_url("reddit_comment:xyz", "", "reddit_post:unknown", {}) == ""
