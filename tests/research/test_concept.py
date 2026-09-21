"""MH-1: concept-grounded hybrid (M3) — criteria store + signal normalization."""

from __future__ import annotations

from src.research.criteria import ConceptCriteria
from src.research.signals import _density, minmax_normalize


def test_detect_virality():
    cc = ConceptCriteria()
    assert cc.detect("what are the top viral topics for pre-dental") == "virality"
    assert cc.detect("most shareable content ideas for applicants") == "virality"
    assert cc.detect("what content resonates with pre-dental students") == "virality"
    assert cc.detect("what are common interview topics") is None


def test_criteria_structure_and_weights():
    cc = ConceptCriteria()
    v = cc.get("virality")
    assert v and len(v["criteria"]) >= 4 and v["sources"] and v["researched_date"]
    assert abs(sum(c["weight"] for c in v["criteria"]) - 1.0) < 1e-6   # weights sum to 1
    assert set(cc.signal_keys("virality")) <= {
        "emotion_intensity", "engagement_score", "advice_density",
        "narrative_density", "social_currency"}


def test_minmax_normalize():
    out = minmax_normalize([{"x": 0.0}, {"x": 5.0}, {"x": 10.0}], ["x"])
    assert [r["x_norm"] for r in out] == [0.0, 0.5, 1.0]
    # constant column -> all zeros (no spurious spread)
    assert all(r["y_norm"] == 0.0 for r in minmax_normalize([{"y": 3}, {"y": 3}], ["y"]))


def test_concept_retrieval_query_strips_meta():
    from src.research.protocol import _concept_retrieval_query
    q = _concept_retrieval_query(
        "what are the top 10 most viral topics for pre-dental to make social media posts about?")
    assert "viral" not in q and "social" not in q and "posts" not in q
    assert "pre-dental" in q and q.startswith("most discussed topics and concerns")


def test_density():
    assert _density(["how to study for the dat", "random text"], ("how to",)) == 0.5
    assert _density([], ("x",)) == 0.0
