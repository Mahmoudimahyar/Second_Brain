"""RA-1: classifier calibration — close the accuracy gate.

The bulk sentiment classifier is a noisy instrument. To turn "44% labelled neutral" into
"the TRUE neutral rate is X% (corrected)", we need its sensitivity/specificity, which need
a labeled reference set. We build a **silver** reference with a stronger model (Llama-3.3-
70B vs the bulk gpt-oss-20b) — explicitly model-vs-model, not human gold — and the harness
accepts human labels as a drop-in. Calibration applies to estimands with a FIXED label
vocabulary (sentiment); open-vocab stance/topic would need per-question gold and stay gated.

Pipeline: reference-label a stratified sample -> confusion -> per-class sens/spec (+SE) ->
Rogan-Gladen correction with a Monte-Carlo CI that propagates both the query's sampling
error and the finite-gold sens/spec uncertainty.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from src.research.stats import rogan_gladen


def one_vs_rest_rates(gold: list[str], pred: list[str]) -> dict[str, dict]:
    """Per-class sensitivity/specificity (+ binomial SE) of the bulk classifier (`pred`)
    treating the reference (`gold`) as truth."""
    out: dict[str, dict] = {}
    for c in sorted(set(gold) | set(pred)):
        tp = sum(1 for g, p in zip(gold, pred) if g == c and p == c)
        fn = sum(1 for g, p in zip(gold, pred) if g == c and p != c)
        tn = sum(1 for g, p in zip(gold, pred) if g != c and p != c)
        fp = sum(1 for g, p in zip(gold, pred) if g != c and p == c)
        n_pos, n_neg = tp + fn, tn + fp
        sens = tp / n_pos if n_pos else None
        spec = tn / n_neg if n_neg else None
        out[c] = {
            "sens": round(sens, 4) if sens is not None else None,
            "spec": round(spec, 4) if spec is not None else None,
            "se_sens": round(math.sqrt(sens * (1 - sens) / n_pos), 4) if sens is not None and n_pos else None,
            "se_spec": round(math.sqrt(spec * (1 - spec) / n_neg), 4) if spec is not None and n_neg else None,
            "n_pos": n_pos, "n_neg": n_neg,
        }
    return out


def cohens_kappa(a: list[str], b: list[str]) -> float:
    """Nominal inter-rater agreement (for when a 2nd reference annotator is added)."""
    n = len(a)
    if n == 0:
        return 0.0
    classes = sorted(set(a) | set(b))
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in classes)
    return round((po - pe) / (1 - pe), 4) if pe < 1 else 1.0


def calibrated_prevalence(p_obs: float, entry: dict, *, p_obs_se: float = 0.0,
                          b: int = 4000, seed: int = 0) -> dict:
    """Rogan-Gladen corrected prevalence with a Monte-Carlo CI propagating (i) the query's
    sampling error `p_obs_se` and (ii) the gold sens/spec uncertainty."""
    sens, spec = entry.get("sens"), entry.get("spec")
    if not sens or not spec or abs(sens + spec - 1) < 1e-6:
        return {"observed": round(p_obs, 4), "mode": "uncalibratable"}
    rng = np.random.default_rng(seed)
    ss = np.clip(rng.normal(sens, (entry.get("se_sens") or 1e-6), b), 0.02, 0.999)
    sp = np.clip(rng.normal(spec, (entry.get("se_spec") or 1e-6), b), 0.02, 0.999)
    po = np.clip(rng.normal(p_obs, p_obs_se or 1e-6, b), 0.0, 1.0)
    denom = ss + sp - 1
    keep = np.abs(denom) > 0.05
    corr = np.clip((po[keep] + sp[keep] - 1) / denom[keep], 0.0, 1.0)
    point = rogan_gladen(p_obs, sens, spec)
    youden = sens + spec - 1                         # classifier informativeness (0..1)
    # A weak classifier (low Youden) or a boundary-clipped point can't pin a prevalence —
    # report the (wide) CI but flag it so we never assert a degenerate 0%/100%.
    reliable = bool(youden >= 0.40 and 0.0 < point < 1.0)
    return {"observed": round(p_obs, 4), "point": round(point, 4),
            "lo": round(float(np.percentile(corr, 2.5)), 4),
            "hi": round(float(np.percentile(corr, 97.5)), 4),
            "mode": "calibrated", "reliable": reliable, "youden": round(youden, 3),
            "sens": sens, "spec": spec,
            "n_gold": entry.get("n_pos", 0) + entry.get("n_neg", 0)}


class CalibrationStore:
    """Persisted {estimand: {class: rates}, "_meta": {...}}; None when absent (-> gated)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {}

    def get(self, estimand: str) -> dict | None:
        return self.data.get(estimand)

    def meta(self) -> dict:
        return self.data.get("_meta", {})

    def save(self, estimand: str, rates: dict, meta: dict) -> None:
        self.data[estimand] = rates
        self.data["_meta"] = {**self.data.get("_meta", {}), **meta}
        self.path.write_text(json.dumps(self.data, indent=2))
