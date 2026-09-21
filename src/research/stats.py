"""Deterministic statistical estimators for the research protocol (numpy + stdlib only).

These are the "instrument calibration" of the system: they turn raw counted buckets into
estimates that carry honest uncertainty, respect non-independence (thread clustering),
shrink small-sample entities, and expose sensitivity to classifier error. No scipy, so it
runs anywhere the bundle does; all randomness is seeded for reproducibility.
"""

from __future__ import annotations

import math

import numpy as np

_Z95 = 1.959963984540054


def _phi(z: float) -> float:
    """Standard normal CDF via erf (no scipy)."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def wilson_ci(k: int, n: int, z: float = _Z95) -> dict:
    """Wilson score interval for a binomial proportion (good at small n / extreme p)."""
    if n <= 0:
        return {"point": 0.0, "lo": 0.0, "hi": 0.0, "k": 0, "n": 0}
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return {"point": round(p, 4), "lo": round(max(0.0, center - margin), 4),
            "hi": round(min(1.0, center + margin), 4), "k": int(k), "n": int(n)}


def cluster_bootstrap_ci(
    clusters: list[list[int]], *, b: int = 2000, seed: int = 0, alpha: float = 0.05,
) -> dict:
    """Thread-clustered bootstrap CI for a proportion.

    `clusters` = one list of 0/1 indicators per thread (membership in the bucket). Reply
    chains echo each other, so we resample THREADS (not comments) — this widens the CI to
    reflect the true effective sample size. Returns the point estimate, percentile CI, the
    design effect, and the effective N = n / deff.
    """
    arrs = [np.asarray(c, dtype=np.float64) for c in clusters if len(c) > 0]
    n = int(sum(a.size for a in arrs))
    if n == 0 or not arrs:
        return {"point": 0.0, "lo": 0.0, "hi": 0.0, "n": 0, "n_eff": 0.0, "deff": 1.0,
                "n_threads": 0}
    point = float(sum(a.sum() for a in arrs) / n)
    rng = np.random.default_rng(seed)
    m = len(arrs)
    sizes = np.array([a.size for a in arrs])
    sums = np.array([a.sum() for a in arrs])
    stats = np.empty(b, dtype=np.float64)
    for i in range(b):
        idx = rng.integers(0, m, size=m)
        stats[i] = sums[idx].sum() / max(1.0, sizes[idx].sum())
    lo, hi = np.percentile(stats, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    var_boot = float(np.var(stats, ddof=1))
    var_srs = point * (1 - point) / n if 0 < point < 1 else 0.0
    deff = (var_boot / var_srs) if var_srs > 0 else 1.0
    n_eff = n / deff if deff > 0 else float(n)
    return {"point": round(point, 4), "lo": round(float(lo), 4), "hi": round(float(hi), 4),
            "n": n, "n_threads": m, "deff": round(deff, 2),
            "n_eff": round(min(float(n), max(1.0, n_eff)), 1)}


def eb_shrink(counts: list[tuple[int, int]]) -> dict:
    """Empirical-Bayes (beta-binomial) shrinkage of per-entity proportions.

    Pulls noisy small-n estimates toward the global mean so a 19-comment school can't top
    or bottom a 119-school ranking by chance. Returns shrunken posterior means + the fitted
    Beta(alpha, beta) prior.
    """
    ps = np.array([k / n for k, n in counts if n > 0], dtype=np.float64)
    if ps.size < 2:
        return {"shrunk": [k / n if n else 0.0 for k, n in counts], "alpha": None, "beta": None}
    m = float(ps.mean())
    v = float(ps.var(ddof=1))
    spread = m * (1 - m)
    if v <= 0 or v >= spread:                       # degenerate -> weak prior, ~no shrink
        alpha = beta = 1.0
    else:
        common = spread / v - 1.0
        alpha = max(1e-6, m * common)
        beta = max(1e-6, (1 - m) * common)
    shrunk = [round((k + alpha) / (n + alpha + beta), 4) if n >= 0 else 0.0 for k, n in counts]
    return {"shrunk": shrunk, "alpha": round(alpha, 3), "beta": round(beta, 3),
            "prior_mean": round(alpha / (alpha + beta), 4)}


def rogan_gladen(p_obs: float, sens: float, spec: float) -> float:
    """Prevalence corrected for an imperfect classifier (sensitivity/specificity)."""
    denom = sens + spec - 1.0
    if abs(denom) < 1e-9:
        return p_obs
    return float(min(1.0, max(0.0, (p_obs + spec - 1.0) / denom)))


def rogan_gladen_band(p_obs: float, *, sens_range=(0.80, 0.95),
                      spec_range=(0.80, 0.95)) -> dict:
    """Range of the corrected prevalence as classifier sens/spec vary over plausible values
    (used when no human gold set is available — sensitivity analysis, not a point claim)."""
    vals = [rogan_gladen(p_obs, s, sp)
            for s in np.linspace(*sens_range, 4) for sp in np.linspace(*spec_range, 4)]
    return {"observed": round(p_obs, 4), "corrected_lo": round(min(vals), 4),
            "corrected_hi": round(max(vals), 4),
            "sens_range": list(sens_range), "spec_range": list(spec_range)}


def consensus_index(props: list[float]) -> dict:
    """How concentrated a stance distribution is. consensus = 1 - normalized entropy;
    HHI = sum p^2; margin = top - runner-up. Distinguishes 80/15/5 from 34/33/33."""
    p = np.array([x for x in props if x > 0], dtype=np.float64)
    if p.size == 0:
        return {"consensus": 0.0, "entropy_norm": 1.0, "hhi": 0.0, "top": 0.0, "margin": 0.0}
    p = p / p.sum()
    h = float(-(p * np.log(p)).sum())
    hmax = math.log(p.size) if p.size > 1 else 1.0
    hn = h / hmax if hmax > 0 else 0.0
    ordered = np.sort(p)[::-1]
    margin = float(ordered[0] - (ordered[1] if ordered.size > 1 else 0.0))
    return {"consensus": round(1 - hn, 4), "entropy_norm": round(hn, 4),
            "hhi": round(float((p * p).sum()), 4), "top": round(float(ordered[0]), 4),
            "margin": round(margin, 4)}


def trend_test(years: list[int], k: list[int], n: list[int]) -> dict:
    """Inverse-variance weighted linear trend of a proportion over years.

    Weight each year by n/(p(1-p)) (a proportion's precision), fit slope, get a z and a
    two-sided p. Tells real drift from noise — the cross-year 'consensus change' test.
    """
    pts = [(y, kk, nn) for y, kk, nn in zip(years, k, n) if nn > 0]
    if len(pts) < 3:
        return {"slope": None, "p": None, "direction": "insufficient_years",
                "years": len(pts)}
    xs = np.array([y for y, _, _ in pts], dtype=np.float64)
    ps = np.array([kk / nn for _, kk, nn in pts], dtype=np.float64)
    ns = np.array([nn for _, _, nn in pts], dtype=np.float64)
    var = ps * (1 - ps) / ns
    var[var <= 0] = float(np.mean(var[var > 0])) if np.any(var > 0) else 1e-6
    w = 1.0 / var
    Sw, Sx, Sy = w.sum(), (w * xs).sum(), (w * ps).sum()
    Sxx, Sxy = (w * xs * xs).sum(), (w * xs * ps).sum()
    d = Sw * Sxx - Sx * Sx
    if abs(d) < 1e-12:
        return {"slope": None, "p": None, "direction": "degenerate", "years": len(pts)}
    slope = (Sw * Sxy - Sx * Sy) / d
    se = math.sqrt(Sw / d)
    z = slope / se if se > 0 else 0.0
    p = 2 * (1 - _phi(abs(z)))
    direction = ("increasing" if slope > 0 else "decreasing") if p < 0.05 else "no_trend"
    return {"slope_per_year": round(float(slope), 5), "se": round(float(se), 5),
            "z": round(float(z), 3), "p": round(float(p), 4),
            "direction": direction, "years": len(pts)}


def resonance(distinct_authors: int, n_threads: int, n_docs: int,
              median_score: float = 0.0) -> dict:
    """Engagement-aware salience of a topic. Distinct authors is primary (one loud user
    can't manufacture a topic); threads + score are secondary signal."""
    return {"distinct_authors": int(distinct_authors), "n_threads": int(n_threads),
            "n_docs": int(n_docs), "median_score": round(float(median_score), 2),
            "author_share": None}
