"""RP-1: statistics toolkit — checked against known/derivable values."""

from __future__ import annotations

from src.research.stats import (
    cluster_bootstrap_ci, consensus_index, eb_shrink, rogan_gladen,
    rogan_gladen_band, trend_test, wilson_ci,
)


def test_wilson_known():
    w = wilson_ci(30, 100)
    assert w["point"] == 0.3
    assert 0.21 < w["lo"] < 0.23 and 0.39 < w["hi"] < 0.41   # Wilson [0.216, 0.398]


def test_wilson_zero_count_has_upper_bound():
    w = wilson_ci(0, 10)
    assert w["point"] == 0.0 and w["lo"] == 0.0 and 0.20 < w["hi"] < 0.35


def test_cluster_bootstrap_singletons_recovers_srs():
    clusters = [[1]] * 30 + [[0]] * 70           # every comment its own thread
    r = cluster_bootstrap_ci(clusters, seed=0)
    assert abs(r["point"] - 0.3) < 1e-9 and r["n"] == 100
    assert r["n_eff"] > 80                        # ~ independent -> n_eff near n
    assert 0.20 < r["lo"] < 0.25 and 0.36 < r["hi"] < 0.41


def test_cluster_bootstrap_clustering_shrinks_neff():
    clusters = [[1] * 10] * 3 + [[0] * 10] * 7    # same 30/70 but in size-10 threads
    r = cluster_bootstrap_ci(clusters, seed=0)
    assert abs(r["point"] - 0.3) < 1e-9
    assert r["n_eff"] < 30 and r["deff"] > 3      # echo within threads -> few effective obs


def test_eb_shrink_pulls_small_n():
    counts = [(1, 2), (200, 1000), (180, 1000), (190, 1000)]
    res = eb_shrink(counts)
    assert res["shrunk"][0] < 0.35               # 0.5 on n=2 pulled toward the ~0.19 mean
    assert abs(res["shrunk"][1] - 0.20) < 0.03   # large-n barely moves


def test_rogan_gladen_point_and_band():
    assert abs(rogan_gladen(0.30, 0.9, 0.9) - 0.25) < 1e-6
    band = rogan_gladen_band(0.30)
    assert band["corrected_lo"] <= 0.30 <= band["corrected_hi"] or band["corrected_hi"] < 0.30


def test_consensus_index_distinguishes():
    hi = consensus_index([0.8, 0.15, 0.05])
    lo = consensus_index([1 / 3, 1 / 3, 1 / 3])
    assert hi["consensus"] > 0.4 and lo["consensus"] < 0.02
    assert hi["margin"] > lo["margin"]


def test_trend_increasing_and_flat():
    inc = trend_test([2018, 2019, 2020, 2021, 2022], [10, 20, 30, 40, 50], [100] * 5)
    assert inc["direction"] == "increasing" and inc["slope_per_year"] > 0 and inc["p"] < 0.05
    flat = trend_test([2018, 2019, 2020, 2021, 2022], [30, 31, 29, 30, 30], [100] * 5)
    assert flat["direction"] == "no_trend"


def test_trend_insufficient_years():
    assert trend_test([2020, 2021], [10, 20], [100, 100])["direction"] == "insufficient_years"
