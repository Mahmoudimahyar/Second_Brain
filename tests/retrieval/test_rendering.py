"""PV-2: deterministic rendering + entailment guard."""

from __future__ import annotations

from src.retrieval.rendering import (
    _fmt_value, allowed_numbers, best_sentence, guard_narration, numbers_in,
    render_grounded_answer,
)


def test_best_sentence_picks_relevant():
    text = ("I love pizza. Shadowing a dentist for 100 hours really helped my "
            "application. The weather was nice that week.")
    out = best_sentence("how do I find shadowing opportunities", text)
    assert "Shadowing" in out and "pizza" not in out


def test_best_sentence_empty():
    assert best_sentence("q", "") == ""
    assert best_sentence("q", None) == ""


def test_best_sentence_no_overlap_falls_back_to_first():
    assert best_sentence("xyzzy plugh", "First here. Second one.").startswith("First")


def test_fmt_value():
    assert _fmt_value("tuition", 98500.0) == "$98,500"
    assert _fmt_value("job_placement_rate", 95.3) == "95.3%"
    assert _fmt_value("interview", True) == "yes"
    assert _fmt_value("is_ivy_league", False) == "no"
    assert _fmt_value("program_length_months", 48) == "48"
    assert _fmt_value("degree_offered", "DMD") == "DMD"


def test_numbers_in_parses_currency_and_pct():
    assert (95000.0, False) in numbers_in("tuition is $95,000 a year")
    assert (30.0, True) in numbers_in("about 30% are negative")


def test_allowed_numbers_from_provenance():
    facts = {"provenance": {"sentiment": [
        {"value": 0.302, "numerator": 1510, "denominator": 5000}]}}
    a = allowed_numbers(facts)
    assert 1510 in a and 5000 in a and 30 in a


def test_guard_drops_unsupported_percentage():
    clean, dropped = guard_narration(
        "30% are negative. A whopping 85% adore it.", {30.0, 1510.0, 5000.0})
    assert any("85%" in d for d in dropped)
    assert "30% are negative." in clean


def test_guard_keeps_supported_percentages():
    clean, dropped = guard_narration(
        "Roughly 30% negative and 17% positive.", {30.0, 17.0})
    assert dropped == [] and "30%" in clean and "17%" in clean


def test_guard_allows_years():
    _clean, dropped = guard_narration("As of 2024 the policy changed.", set())
    assert dropped == []          # 2024 is a year, not a statistic


def test_guard_flags_unsupported_big_count():
    _clean, dropped = guard_narration("There are 500 dental schools.", {3.0, 4.0})
    assert dropped               # 500 not supported by the facts


def test_render_grounded_answer_is_counted():
    md = render_grounded_answer({
        "answered": True, "verdict": {},
        "provenance": {"sentiment": [
            {"label": "positive", "value": 0.17, "numerator": 850, "denominator": 5000}]}})
    assert "5,000" in md and "17% positive" in md and "850" in md


def test_render_grounded_answer_abstain_keeps_breakdown():
    md = render_grounded_answer({
        "answered": False, "abstain_reason": "evidence too thin",
        "provenance": {"opinion": [
            {"label": "x", "value": 0.5, "numerator": 5, "denominator": 10}]},
        "verdict": {"authoritative_answer": "should be hidden"}})
    assert "evidence too thin" in md
    assert "should be hidden" not in md     # no verdict when abstaining
    assert "50% x" in md                    # breakdown still shown
