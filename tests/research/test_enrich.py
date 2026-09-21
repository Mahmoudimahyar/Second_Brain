"""RP-2: enrichment — year/subreddit/cohort/price + metadata join."""

from __future__ import annotations

import sqlite3

from src.research.enrich import (
    clusters_for, cohort_of, enrich_items, extract_prices, is_junk, subreddit_of, year_of,
)


def test_is_junk():
    assert is_junk("[removed]", "user") and is_junk("[deleted]", "user")
    assert is_junk("anything at all here", "AutoModerator")
    assert is_junk("ok", "user")                                  # too short
    assert is_junk("Your post has been removed because of rule 3", "user")
    assert not is_junk("I struggled with the DAT, here is my advice for studying", "user")


def test_year_of():
    assert year_of("2009-03-05T07:36:22+00:00") == 2009
    assert year_of("") is None and year_of("abcd-1") is None and year_of("1850-01") is None


def test_subreddit_and_cohort():
    assert subreddit_of("/r/predental/comments/p1/t/") == "predental"
    assert subreddit_of("https://www.reddit.com/r/DentalSchool/comments/x/") == "DentalSchool"
    assert subreddit_of("") is None
    assert cohort_of("predental") == "pre-dental applicant"
    assert cohort_of("Dentistry") == "practicing/professional"
    assert cohort_of("someothersub") == "r/someothersub"
    assert cohort_of(None) == "unknown"


def test_extract_prices():
    got = extract_prices("I paid $1,500 for an advisor, a friend paid $300, another $2k")
    assert got == [1500.0, 300.0, 2000.0]
    assert extract_prices("it cost $5 and happened in 2009") == []   # below floor / no $ on year


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE documents(doc_id TEXT, doc_type TEXT, thread_id TEXT, "
                "author TEXT, created_iso TEXT, score INT, url TEXT)")
    con.executemany(
        "INSERT INTO documents(doc_id,doc_type,thread_id,author,created_iso,score,url) "
        "VALUES (?,?,?,?,?,?,?)", [
            ("reddit_post:p1", "reddit_post", "reddit_post:p1", "alice",
             "2021-05-01T00:00:00+00:00", 5, "/r/predental/comments/p1/title/"),
            ("reddit_comment:c1", "reddit_comment", "reddit_post:p1", "bob",
             "2021-06-01T00:00:00+00:00", 2, ""),
            ("reddit_comment:c2", "reddit_comment", "reddit_post:p1", "[deleted]",
             "2022-06-01T00:00:00+00:00", 1, ""),
        ])
    con.commit()
    return con


def test_enrich_items_inherits_cohort_and_parses_year():
    items = enrich_items(_db(), {"reddit_post:p1": "pos", "reddit_comment:c1": "neg",
                                 "reddit_comment:c2": "pos"})
    by = {it["doc_id"]: it for it in items}
    assert by["reddit_post:p1"]["cohort"] == "pre-dental applicant"
    assert by["reddit_post:p1"]["year"] == 2021
    # comment inherits the parent post's subreddit cohort (it has no URL of its own)
    assert by["reddit_comment:c1"]["cohort"] == "pre-dental applicant"
    assert by["reddit_comment:c1"]["author"] == "bob"
    assert by["reddit_comment:c2"]["author"] is None    # [deleted] dropped
    assert by["reddit_comment:c1"]["bucket"] == "neg"


def test_clusters_for_groups_by_thread():
    items = [{"thread_id": "t1", "bucket": "pos"}, {"thread_id": "t1", "bucket": "neg"},
             {"thread_id": "t2", "bucket": "pos"}]
    cl = clusters_for(items, "pos")
    assert sorted([sorted(c) for c in cl]) == [[0, 1], [1]]   # t1 -> [1,0], t2 -> [1]
