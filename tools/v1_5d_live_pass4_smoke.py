"""V1.5d B6 — live Pass-4 sentiment quality-lift smoke (analog of W1-8).

Loads ``.env``, unsets ``SECBRAIN_OFFLINE``, constructs a real
``ModelGateway`` (Haiku 4.5), then runs each row of
``evals/gold/sentiment.jsonl`` through ``extract_sentiment`` and
reports accuracy + cost + latency.

This is the live verification gate that proves the production Pass-4
sentiment path (utility filter → cache → gateway → audit) actually
classifies real prose at the gateway-routed model. Closes W1-7's
original intent (a live quality-lift smoke analogous to the Tavily
smoke that closed W1-8).

Usage:

    .venv/Scripts/python.exe -m tools.v1_5d_live_pass4_smoke

Costs ~$0.001-0.005 per row via Haiku 4.5 (Pass-4 prompts are short);
12-row run runs ~$0.05-0.20 total.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

# Load .env into os.environ before importing anything that reads keys.
for line in Path(".env").read_text().splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if k and v:
            os.environ[k] = v
os.environ.pop("SECBRAIN_OFFLINE", None)


from src.extraction.cache import ExtractionCache  # noqa: E402
from src.extraction.pass4_runners import extract_sentiment  # noqa: E402
from src.gateway.api import default_gateway  # noqa: E402

GOLD_PATH = Path("evals/gold/sentiment.jsonl")


def main() -> int:
    rows = [
        json.loads(line) for line in GOLD_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(rows) == 0:
        print(f"ERROR: gold set at {GOLD_PATH} is empty")
        return 2

    gateway = default_gateway()
    # Use a temp cache so the smoke always hits the live LLM (no replay).
    # ignore_cleanup_errors=True handles Windows SQLite-handle release races.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        cache = ExtractionCache(sqlite_path=Path(td) / "pass4-cache.db")
        results: list[tuple[str, str, str, float, int, bool]] = []
        total_cost = 0.0
        for i, row in enumerate(rows, 1):
            text = str(row["text"])
            expected = str(row["expected_verdict"]).lower()
            t0 = time.perf_counter()
            outcome = extract_sentiment(
                text,
                gateway=gateway,
                cache=cache,
            )
            dt_ms = int((time.perf_counter() - t0) * 1000)
            sent = outcome.parsed
            verdict = getattr(sent, "verdict", "").lower() if sent else "n/a"
            ok = verdict == expected
            total_cost += outcome.cost_usd or 0.0
            results.append((text[:60], expected, verdict, outcome.cost_usd or 0.0, dt_ms, ok))
            print(
                f"  {i:2d}. {'OK ' if ok else 'XX '} "
                f"expected={expected:<8} got={verdict:<8} "
                f"cost=${outcome.cost_usd or 0:.4f} {dt_ms:>4}ms "
                f"text={text[:60]!r}",
            )

    n = len(results)
    correct = sum(1 for r in results if r[5])
    print()
    print(f"Pass-4 live smoke: {correct}/{n} correct ({correct / n:.0%})")
    print(f"Total cost: ${total_cost:.4f}")
    # AC: ≥ 75% sentiment accuracy on this gold set (12 rows, 9+ correct).
    threshold = 0.75
    if correct / n < threshold:
        print(f"FAIL: accuracy {correct / n:.0%} below threshold {threshold:.0%}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
