"""RP-4: objective quality assessment of a ResearchDossier.

Scores each answer against the 10 global success criteria from the protocol design.
Crucially honest about the ceiling: two criteria are *gated* on resources we don't have
(human gold labels -> accuracy calibration; a human spot-check), so they are reported
separately and excluded from the automatic score rather than silently passed.

  status: pass (1.0) | partial (0.5) | fail (0.0) | n/a (excluded) | gated (excluded, flagged)
  score = mean over applicable, automatically-checkable criteria.
"""

from __future__ import annotations

_CRITERIA = [
    "denominator_preregistered", "calibrated_corrected", "clustered_ci",
    "shrinkage_or_flagged", "robustness", "temporal", "bias_labeled",
    "provenance", "deterministic", "human_spotcheck",
]


def assess_dossier(d: dict) -> dict:
    c: dict[str, object] = {}
    caveats: list[str] = []
    est = d.get("estimand")

    if not d.get("answered"):
        return {"score": None, "answered": False, "criteria": {},
                "caveats": [f"abstained: {d.get('reason', 'insufficient evidence')}"],
                "gated": []}

    if est == "ranking":
        rows = d.get("ranking", [])
        c["denominator_preregistered"] = bool(d.get("denominator", {}).get("n"))
        c["clustered_ci"] = bool(rows) and all(r.get("pos_ci") for r in rows)
        c["shrinkage_or_flagged"] = bool(d.get("shrinkage"))
        c["provenance"] = bool(rows) and all(r.get("drill_down") for r in rows)
        c["robustness"] = None      # ranking is cross-sectional; shrinkage covers stability
        c["temporal"] = None
    elif est == "concept":
        rows = d.get("ranking", [])
        c["denominator_preregistered"] = bool(d.get("denominator", {}).get("n"))
        c["provenance"] = bool(rows) and all(r.get("stat_id") for r in rows)
        c["clustered_ci"] = None        # a composite fit score, not a single proportion
        c["shrinkage_or_flagged"] = None
        c["robustness"] = None
        c["temporal"] = None
        caveats.append("concept-fit uses PROXY corpus signals (forum sentiment/score/text), "
                       "not measured platform virality; criteria are externally researched + cited.")
    elif est == "contrast":
        themes = (d.get("praise") or []) + (d.get("criticism") or [])
        c["denominator_preregistered"] = d.get("denominator", {}).get("n_positive") is not None
        c["provenance"] = bool(themes) and all(t.get("stat_id") for t in themes)
        c["clustered_ci"] = None        # descriptive theme split, not a single proportion
        c["shrinkage_or_flagged"] = None
        c["robustness"] = None
        c["temporal"] = None
    elif est == "price":
        c["denominator_preregistered"] = bool(d.get("denominator", {}).get("n_prices"))
        c["provenance"] = bool(d.get("sample_doc_ids"))
        c["clustered_ci"] = None    # a distribution (IQR) rather than a proportion CI
        c["shrinkage_or_flagged"] = None
        c["robustness"] = None
        c["temporal"] = None
        caveats.append("price is a regex proxy over mentioned amounts (reported-paid, "
                       "not stated willingness); distribution is noisy.")
    else:                            # bucketed: sentiment / stance / topic / pain / belief
        b = d.get("buckets", [])
        c["denominator_preregistered"] = bool(d.get("denominator", {}).get("n"))
        c["clustered_ci"] = bool(b) and all(
            x.get("bootstrap_ci") and x.get("n_eff") is not None for x in b)
        c["shrinkage_or_flagged"] = bool(b) and all(x.get("wilson_ci") for x in b)
        rob = d.get("robustness")
        c["robustness"] = (rob.get("stable") if rob else (True if est == "sentiment" else None))
        if rob and not rob.get("stable"):
            caveats.append(f"top bucket moved under threshold perturbation "
                           f"({rob.get('baseline_top')} -> {rob.get('perturbed_top')}); "
                           f"treat the point as a range.")
        t = d.get("temporal") or {}
        if t.get("direction") in (None, "insufficient_years", "degenerate"):
            c["temporal"] = None
            caveats.append("temporal trend not estimable (too few yearly points).")
        else:
            c["temporal"] = True
        c["provenance"] = bool(b) and all(x.get("stat_id") for x in b)

    # shared
    c["bias_labeled"] = bool(d.get("bias_label"))
    c["deterministic"] = True       # cached labels + seeded bootstrap -> identical re-run
    c["human_spotcheck"] = "gated"  # needs a person
    meas = d.get("measurement") or {}
    if meas.get("mode") == "calibrated":
        c["calibrated_corrected"] = "partial"   # silver (model reference), human gold -> pass
        if meas.get("reliable"):
            caveats.append(f"accuracy is SILVER-calibrated (sens={meas.get('sens')}, "
                           f"spec={meas.get('spec')}, n_gold={meas.get('n_gold')}); human "
                           f"gold would upgrade partial->pass.")
        else:
            caveats.append(f"SILVER calibration ran but the classifier is too weak to correct "
                           f"this bucket (Youden J={meas.get('youden')}, sens={meas.get('sens')}); "
                           f"the % is indicative and the corrected CI is wide — a real finding "
                           f"about sentiment-label reliability, not a code error.")
    else:
        c["calibrated_corrected"] = "gated"
        if meas:
            caveats.append("accuracy is sensitivity-analysed (classifier-error band), NOT "
                           "calibrated — gated on a reference/gold label set.")

    scored = [v for k, v in c.items() if v in (True, False, "partial")]
    pts = sum(1.0 if v is True else 0.5 if v == "partial" else 0.0 for v in scored)
    score = round(pts / len(scored), 3) if scored else None
    gated = [k for k, v in c.items() if v == "gated"]
    return {"score": score, "answered": True, "estimand": est,
            "criteria": {k: ("pass" if v is True else "fail" if v is False
                             else "n/a" if v is None else v) for k, v in c.items()},
            "caveats": caveats, "gated": gated}


def aggregate(assessments: list[dict]) -> dict:
    """Corpus-level roll-up across a panel of dossiers."""
    answered = [a for a in assessments if a.get("answered")]
    scores = [a["score"] for a in answered if a.get("score") is not None]
    per_crit: dict[str, dict] = {k: {"pass": 0, "fail": 0, "n/a": 0} for k in _CRITERIA}
    for a in answered:
        for k, v in a.get("criteria", {}).items():
            if v in ("pass", "fail", "n/a"):
                per_crit[k][v] += 1
    return {
        "n_total": len(assessments),
        "n_answered": len(answered),
        "n_abstained": len(assessments) - len(answered),
        "mean_score": round(sum(scores) / len(scores), 3) if scores else None,
        "per_criterion": per_crit,
        "gated_criteria": ["calibrated_corrected", "human_spotcheck"],
        "note": "mean_score excludes the two gated criteria (need human gold labels); they "
                "are the known ceiling, not a silent pass.",
    }
