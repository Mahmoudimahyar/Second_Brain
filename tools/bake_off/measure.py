"""Common measurement helpers + result schema for the bake-off."""

from __future__ import annotations

import json
import statistics
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class QueryResult:
    name: str
    sample_size: int
    latencies_ms: list[float]

    @property
    def median_ms(self) -> float:
        return statistics.median(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def p95_ms(self) -> float:
        return _percentile(self.latencies_ms, 95) if self.latencies_ms else 0.0


@dataclass
class EngineMeasurement:
    engine: str
    status: str  # "ok" | "skipped" | "failed"
    notes: str = ""

    # M1 — bulk load
    bulk_load_seconds: float = 0.0
    nodes_loaded: int = 0
    edges_loaded: int = 0
    rss_peak_mb: float = 0.0
    disk_footprint_mb: float = 0.0

    # M2 — 3-hop latency
    queries: list[QueryResult] = field(default_factory=list)

    # M3 — HNSW recall@10
    hnsw_recall_at_10: float | None = None
    hnsw_supported: bool | None = None

    # M4 — bitemporal ergonomics (subjective 1-5 per test-plan.md)
    bitemporal_score: int | None = None
    bitemporal_notes: str = ""

    # M5 — ops complexity (subjective 1-5)
    ops_score: int | None = None
    ops_notes: str = ""

    measured_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def time_it(fn: Callable[[], Any]) -> tuple[float, Any]:
    start = time.perf_counter()
    result = fn()
    return (time.perf_counter() - start) * 1000.0, result


def _percentile(data: list[float], percent: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * percent / 100
    f = int(k)
    c = min(f + 1, len(sorted_data) - 1)
    return sorted_data[f] + (sorted_data[c] - sorted_data[f]) * (k - f)


def run_query_n(name: str, fn: Callable[[], Any], iterations: int) -> QueryResult:
    """Warm-up 3x, then time `iterations` runs. Returns latencies."""

    for _ in range(3):
        fn()
    latencies: list[float] = []
    for _ in range(iterations):
        ms, _ = time_it(fn)
        latencies.append(ms)
    return QueryResult(name=name, sample_size=iterations, latencies_ms=latencies)


def write_result(measurement: EngineMeasurement, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = asdict(measurement)
    payload["queries"] = [
        {
            "name": q.name,
            "sample_size": q.sample_size,
            "median_ms": q.median_ms,
            "p95_ms": q.p95_ms,
        }
        for q in measurement.queries
    ]
    payload["measured_at"] = measurement.measured_at.isoformat()
    out_path.write_text(json.dumps(payload, indent=2))


def _percentile_dict(qr: QueryResult) -> dict[str, float]:
    return {"median_ms": qr.median_ms, "p95_ms": qr.p95_ms}
