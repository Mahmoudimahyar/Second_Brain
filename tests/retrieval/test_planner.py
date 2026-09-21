"""PV-4: compositional query planner — gating, plan parsing, deterministic execution."""

from __future__ import annotations

from src.retrieval.planner import (
    _heuristic_plan, _parse_plan, execute_plan, is_ranking_query,
)


def test_is_ranking_query():
    assert is_ranking_query("what are the cheapest dental schools")
    assert is_ranking_query("worst reviewed dental schools")
    assert is_ranking_query("which schools do applicants like best")
    assert not is_ranking_query("how do applicants view NYU College of Dentistry")
    assert not is_ranking_query("what are common interview questions")


def test_heuristic_plan_cheapest():
    p = _heuristic_plan("what are the cheapest dental schools")
    assert p["ops"][0]["op"] == "rank_tuition" and p["ops"][0]["order"] == "asc"
    assert p["combine"] is None and p["sort_by"] == "tuition"


def test_heuristic_plan_worst_reviewed():
    p = _heuristic_plan("worst reviewed dental schools")
    assert p["ops"][0]["op"] == "rank_sentiment" and p["ops"][0]["order"] == "asc"


def test_heuristic_plan_compositional_intersect():
    p = _heuristic_plan("cheapest schools that applicants also like")
    assert {o["op"] for o in p["ops"]} == {"rank_tuition", "rank_sentiment"}
    assert p["combine"] == "intersect"


def test_parse_plan():
    assert _parse_plan('{"ops":[{"op":"rank_tuition","order":"asc","k":5}]}')["ops"]
    assert _parse_plan("```json\n{\"ops\":[]}\n```") == {"ops": []}
    assert _parse_plan("not json at all") is None


class _FakeMetrics:
    UNIV = [("s1", "A", 30000, 100, 0.30),
            ("s2", "B", 40000, 50, 0.20),
            ("s3", "C", 50000, 80, 0.25)]

    def available(self):
        return True

    def rank_tuition(self, order, k):
        return sorted(self.UNIV, key=lambda r: r[2], reverse=(order == "desc"))[:k]

    def rank_sentiment(self, order, k, *, min_comments=50):
        rows = [r for r in self.UNIV if r[3] >= min_comments]
        return sorted(rows, key=lambda r: r[4], reverse=(order == "desc"))[:k]


def test_execute_plan_intersect_true_join():
    plan = {"ops": [{"op": "rank_tuition", "order": "asc", "k": 2},
                    {"op": "rank_sentiment", "order": "desc", "k": 2}],
            "combine": "intersect", "sort_by": "tuition"}
    res = execute_plan(plan, _FakeMetrics())
    # cheapest-2 {s1,s2} ∩ most-liked-2 {s1,s3} = {s1}
    assert [r["school_id"] for r in res["ranking"]] == ["s1"]


def test_execute_plan_worst_reviewed_ascending():
    plan = {"ops": [{"op": "rank_sentiment", "order": "asc", "k": 3}],
            "combine": None, "sort_by": "sentiment"}
    res = execute_plan(plan, _FakeMetrics())
    # ascending pos_frac: s2(.20) < s3(.25) < s1(.30)
    assert [r["school_id"] for r in res["ranking"]] == ["s2", "s3", "s1"]


def test_execute_plan_cheapest_ascending():
    plan = {"ops": [{"op": "rank_tuition", "order": "asc", "k": 3}],
            "combine": None, "sort_by": "tuition"}
    res = execute_plan(plan, _FakeMetrics())
    assert [r["school_id"] for r in res["ranking"]] == ["s1", "s2", "s3"]


def test_execute_plan_empty_ops_returns_none():
    assert execute_plan({"ops": []}, _FakeMetrics()) is None
