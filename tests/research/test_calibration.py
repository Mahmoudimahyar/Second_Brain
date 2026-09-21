"""RA-1: calibration — confusion rates, kappa, Rogan-Gladen correction, store."""

from __future__ import annotations

from src.research.calibration import (
    CalibrationStore, calibrated_prevalence, cohens_kappa, one_vs_rest_rates,
)


def test_one_vs_rest_rates():
    gold = ["pos", "pos", "neg", "neg"]
    pred = ["pos", "neg", "neg", "neg"]
    r = one_vs_rest_rates(gold, pred)
    assert r["pos"]["sens"] == 0.5 and r["pos"]["spec"] == 1.0        # tp1/fn1; tn2/fp0
    assert r["neg"]["sens"] == 1.0 and r["neg"]["spec"] == 0.5        # tp2/fn0; tn1/fp1
    assert r["pos"]["n_pos"] == 2 and r["pos"]["n_neg"] == 2


def test_cohens_kappa():
    assert cohens_kappa(["a", "b", "a"], ["a", "b", "a"]) == 1.0
    assert cohens_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) < 0.3   # ~chance


def test_calibrated_prevalence_corrects_and_bands():
    entry = {"sens": 0.9, "spec": 0.9, "se_sens": 0.02, "se_spec": 0.02,
             "n_pos": 100, "n_neg": 100}
    m = calibrated_prevalence(0.30, entry, p_obs_se=0.01)
    assert m["mode"] == "calibrated"
    assert abs(m["point"] - 0.25) < 0.01                    # rogan_gladen(0.3,0.9,0.9)
    assert m["lo"] < m["point"] < m["hi"] and m["n_gold"] == 200


def test_calibrated_low_reliability_flagged():
    weak = {"sens": 0.438, "spec": 0.864, "se_sens": 0.05, "se_spec": 0.03,
            "n_pos": 121, "n_neg": 199}                          # Youden ~0.30
    m = calibrated_prevalence(0.44, weak)
    assert m["mode"] == "calibrated" and m["reliable"] is False and m["youden"] < 0.4
    strong = {"sens": 0.9, "spec": 0.92, "se_sens": 0.02, "se_spec": 0.02,
              "n_pos": 150, "n_neg": 150}
    assert calibrated_prevalence(0.30, strong)["reliable"] is True


def test_calibrated_prevalence_uncalibratable():
    assert calibrated_prevalence(0.3, {"sens": 0.5, "spec": 0.5})["mode"] == "uncalibratable"


def test_store_roundtrip(tmp_path):
    p = tmp_path / "cal.json"
    s = CalibrationStore(p)
    assert s.get("sentiment") is None
    s.save("sentiment", {"positive": {"sens": 0.9, "spec": 0.9}}, {"n": 200, "kind": "silver"})
    s2 = CalibrationStore(p)
    assert s2.get("sentiment")["positive"]["sens"] == 0.9
    assert s2.meta()["kind"] == "silver"
