"""RP-3: estimand routing + deterministic answer rendering (pure, no engine)."""

from __future__ import annotations

import pytest

from src.research.protocol import classify_estimand, render_research_answer


@pytest.mark.parametrize("q,est", [
    ("How do applicants view NYU College of Dentistry?", "sentiment"),
    ("Is NYU worth the cost?", "stance"),
    ("What are common dental school interview topics?", "topic"),
    ("What are the cheapest dental schools that applicants also like?", "ranking"),
    ("Which dental schools are the worst reviewed?", "ranking"),
    ("How much are applicants comfortable paying for advising services?", "price"),
    ("What are the top pain points pre-dental applicants face?", "pain"),
    ("What are the top 5 use cases people would pay a product to solve?", "topic"),
    ("What do applicants get wrong about dental school admissions?", "belief"),
    ("What's the most talked about topic among pre-dental students in July?", "topic"),
    ("What do applicants praise versus criticize about NYU dental?", "contrast"),
    ("What are the pros and cons of NYU according to applicants?", "contrast"),
])
def test_estimand_routing(q, est):
    assert classify_estimand(q)[0] == est


def test_target_cohorts():
    from src.research.protocol import _target_cohorts
    assert _target_cohorts("biggest pain points for dental school applicants") == {
        "pre-dental applicant", "dental student", "sdn"}
    assert _target_cohorts("what do OMFS residents worry about") is None      # professional
    assert _target_cohorts("patient experience with crowns") is None          # clinical


def test_price_routing_magnitude_only():
    # "how much" -> price; "worth paying for vs free" is a value judgement, NOT price
    assert classify_estimand("How much do people pay for advising?")[0] == "price"
    assert classify_estimand("What is worth paying for versus should be free?")[0] != "price"


def test_flags():
    _e, f = classify_estimand("most talked about topic among pre-dental students in July")
    assert f["temporal"] and f["segment"]
    _e, f2 = classify_estimand("how much would OMFS residents pay")
    assert f2["price"] and f2["segment"]


def test_render_not_answered():
    assert "No defensible answer" in render_research_answer({"answered": False, "reason": "x"})


def test_render_sentiment_has_ci():
    d = {"answered": True, "estimand": "sentiment",
         "denominator": {"n": 100, "n_threads": 40, "n_authors": 50},
         "buckets": [{"label": "positive", "point": 0.3, "bootstrap_ci": [0.22, 0.39],
                      "n_eff": 35, "k": 30}],
         "consensus": {"consensus": 0.1, "margin": 0.1},
         "measurement": {"corrected_lo": 0.22, "corrected_hi": 0.40},
         "bias_label": "B", "provenance_note": "P"}
    out = render_research_answer(d)
    assert "30%" in out and "95% CI" in out and "n_eff" in out
