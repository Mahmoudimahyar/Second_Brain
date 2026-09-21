"""Compute the bake-off weighted score per `docs/05-features/bake-off-graph-db/test-plan.md`."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Weights from `docs/05-features/bake-off-graph-db/README.md`:
_WEIGHTS = {
    "M1_load": 0.20,
    "M2_three_hop_p95": 0.25,
    "M3_hnsw_recall_at_10": 0.20,
    "M4_bitemporal_score": 0.20,
    "M5_ops_score": 0.15,
}

_LOWER_IS_BETTER = {"M1_load", "M2_three_hop_p95"}


@dataclass
class CandidateScore:
    engine: str
    raw: dict[str, float]
    normalized: dict[str, float]
    weighted_total: float


def _normalize_metric(values: dict[str, float], lower_better: bool) -> dict[str, float]:
    finite = {k: v for k, v in values.items() if v is not None}
    if not finite:
        return {k: 0.0 for k in values}
    lo, hi = min(finite.values()), max(finite.values())
    if hi == lo:
        return {k: 1.0 for k in values}
    out: dict[str, float] = {}
    for k, v in values.items():
        if v is None:
            out[k] = 0.0
            continue
        if lower_better:
            out[k] = (hi - v) / (hi - lo)
        else:
            out[k] = (v - lo) / (hi - lo)
    return out


def _three_hop_p95(measurement: dict[str, Any]) -> float | None:
    """Pick the Q-A (3-hop) p95 latency."""

    for q in measurement.get("queries", []):
        if q.get("name", "").startswith("Q-A"):
            return float(q.get("p95_ms", 0))
    return None


def _hnsw(measurement: dict[str, Any]) -> float:
    """Default to 1.0 — all 5.x engines have HNSW; recall@10 measured offline."""

    val = measurement.get("hnsw_recall_at_10")
    if val is None:
        return 1.0
    return float(val)


def score_all(result_dir: Path) -> list[CandidateScore]:
    measurements: dict[str, dict[str, Any]] = {}
    for path in sorted(result_dir.glob("*.json")):
        engine = path.stem
        measurements[engine] = json.loads(path.read_text(encoding="utf-8"))

    raw_metrics: dict[str, dict[str, float | None]] = {
        "M1_load": {e: float(m.get("bulk_load_seconds", 0)) for e, m in measurements.items()},
        "M2_three_hop_p95": {e: _three_hop_p95(m) for e, m in measurements.items()},
        "M3_hnsw_recall_at_10": {e: _hnsw(m) for e, m in measurements.items()},
        "M4_bitemporal_score": {e: float(m.get("bitemporal_score") or 0) for e, m in measurements.items()},
        "M5_ops_score": {e: float(m.get("ops_score") or 0) for e, m in measurements.items()},
    }

    normalized: dict[str, dict[str, float]] = {}
    for metric, values in raw_metrics.items():
        normalized[metric] = _normalize_metric(values, lower_better=(metric in _LOWER_IS_BETTER))

    scores: list[CandidateScore] = []
    for engine in measurements:
        weighted = sum(
            _WEIGHTS[metric] * normalized[metric][engine] for metric in _WEIGHTS
        )
        scores.append(
            CandidateScore(
                engine=engine,
                raw={k: float(v[engine] or 0) for k, v in raw_metrics.items()},
                normalized={k: float(v[engine]) for k, v in normalized.items()},
                weighted_total=weighted,
            )
        )
    scores.sort(key=lambda s: s.weighted_total, reverse=True)
    return scores


def tiebreak(scores: list[CandidateScore]) -> tuple[CandidateScore, str]:
    """Per `decisions.md`: if margin between #1 and #2 < 0.10, M5 ops complexity tiebreaks."""

    if len(scores) < 2:
        return scores[0], "single candidate"
    a, b = scores[0], scores[1]
    margin = a.weighted_total - b.weighted_total
    if margin >= 0.10:
        return a, f"{a.engine} wins by {margin:.3f} (clear margin)"
    # M5 tiebreak
    if a.raw["M5_ops_score"] >= b.raw["M5_ops_score"]:
        return a, f"margin {margin:.3f} < 0.10 ->M5 ops tiebreak kept {a.engine}"
    return b, f"margin {margin:.3f} < 0.10 ->M5 ops tiebreak flipped to {b.engine}"


def main() -> int:
    result_dir = Path("tools/bake_off/results")
    scores = score_all(result_dir)
    winner, reason = tiebreak(scores)
    print("Engine          | M1 load (s) | M2 3hop p95 (ms) | M4 bitemp | M5 ops | total")
    print("-" * 80)
    for s in scores:
        print(
            f"{s.engine:15s} | {s.raw['M1_load']:11.2f} | {s.raw['M2_three_hop_p95']:16.2f} "
            f"| {s.raw['M4_bitemporal_score']:9.0f} | {s.raw['M5_ops_score']:6.0f} | {s.weighted_total:.3f}"
        )
    print()
    print(f"WINNER: {winner.engine} ({reason})")
    summary = {
        "scores": [
            {
                "engine": s.engine,
                "raw": s.raw,
                "normalized": s.normalized,
                "weighted_total": s.weighted_total,
            }
            for s in scores
        ],
        "winner": winner.engine,
        "tiebreak_reason": reason,
    }
    Path("tools/bake_off/results/_summary.json").write_text(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
