"""RP-4: quality assessor — scoring + gated-criteria honesty."""

from __future__ import annotations

from src.research.quality import aggregate, assess_dossier

_BUCKETED = {
    "answered": True, "estimand": "stance",
    "denominator": {"n": 4000, "n_threads": 1380, "n_authors": 776},
    "buckets": [{"label": "a", "wilson_ci": [0.9, 0.94], "bootstrap_ci": [0.91, 0.94],
                 "n_eff": 1776, "stat_id": "stat:x"}],
    "consensus": {"consensus": 0.75}, "measurement": {"corrected_lo": 0.97, "corrected_hi": 1.0},
    "temporal": {"direction": "decreasing", "p": 0.0},
    "robustness": {"stable": True, "baseline_top": 0.93, "perturbed_top": 0.9},
    "bias_label": "B",
}


def test_assess_bucketed_passes_checkable_and_gates_calibration():
    a = assess_dossier(_BUCKETED)
    assert a["score"] is not None and a["score"] > 0.8
    assert a["criteria"]["clustered_ci"] == "pass"
    assert a["criteria"]["provenance"] == "pass"
    assert a["criteria"]["temporal"] == "pass"
    assert "calibrated_corrected" in a["gated"]        # not silently passed
    assert any("gated" in c or "calibrat" in c for c in a["caveats"])


def test_assess_calibrated_is_partial_not_gated():
    d = dict(_BUCKETED, measurement={"mode": "calibrated", "point": 0.42, "lo": 0.39,
                                     "hi": 0.45, "sens": 0.88, "spec": 0.91, "n_gold": 300})
    a = assess_dossier(d)
    assert a["criteria"]["calibrated_corrected"] == "partial"
    assert "calibrated_corrected" not in a["gated"]
    assert any("SILVER" in c for c in a["caveats"])


def test_assess_flags_unstable_robustness():
    d = dict(_BUCKETED, robustness={"stable": False, "baseline_top": 0.93, "perturbed_top": 0.72})
    a = assess_dossier(d)
    assert a["criteria"]["robustness"] == "fail"
    assert any("threshold perturbation" in c for c in a["caveats"])


def test_assess_ranking():
    d = {"answered": True, "estimand": "ranking",
         "denominator": {"n": 17}, "shrinkage": {"prior_mean": 0.19},
         "ranking": [{"pos_ci": [0.18, 0.26], "drill_down": "/x"}]}
    a = assess_dossier(d)
    assert a["criteria"]["shrinkage_or_flagged"] == "pass"
    assert a["criteria"]["clustered_ci"] == "pass"


def test_assess_abstained():
    a = assess_dossier({"answered": False, "reason": "no evidence"})
    assert a["score"] is None and not a["answered"]


def test_aggregate():
    agg = aggregate([assess_dossier(_BUCKETED), assess_dossier({"answered": False, "reason": "x"})])
    assert agg["n_total"] == 2 and agg["n_answered"] == 1 and agg["n_abstained"] == 1
    assert agg["mean_score"] is not None
