"""V1.5c W1-8 — live Tavily smoke against the 5-clash gold set.

Loads ``.env``, unsets ``SECBRAIN_OFFLINE``, constructs a
``WebVerificationAgent`` wired to the real Tavily provider and the
real gateway (Haiku 4.5 + Gemini Flash), then runs each gold claim
through ``verify_claim`` and reports verdict + cost + latency.

This is the live verification gate that closes V1.5c AC-1 — proves
the production code path (W1-1 + W1-2 remediation) actually resolves
real-world claims via real LLM judgments.

Usage:

    .venv/Scripts/python.exe -m tools.v1_5c_live_tavily_smoke

Costs ~$0.05-0.20 per claim; default cap $5/run.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Load .env into os.environ before importing anything that reads keys.
for line in Path(".env").read_text().splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if k and v:
            os.environ[k] = v
os.environ.pop("SECBRAIN_OFFLINE", None)


from src.conflict.providers.tavily import TavilyProvider  # noqa: E402
from src.conflict.web_verify import (  # noqa: E402
    CostBudget,
    WebVerificationAgent,
)
from src.gateway.api import default_gateway  # noqa: E402

GOLD_PATH = Path("evals/gold/v1.5c-web-verify.jsonl")


def main() -> int:
    rows = [
        json.loads(line) for line in GOLD_PATH.read_text().splitlines()
        if line.strip()
    ]
    assert len(rows) == 5, f"expected 5 gold rows, got {len(rows)}"

    # Cost-tracking: TavilyProvider.cost_callback writes to this list.
    cost_log: list[tuple[str, float]] = []

    def _cost_cb(op: str, cost: float) -> None:
        cost_log.append((op, cost))

    provider = TavilyProvider(
        cost_callback=_cost_cb,
    )
    gateway = default_gateway()

    agent = WebVerificationAgent(
        provider=provider,
        cost_budget=CostBudget(cap_usd=5.0),
    )
    # `verify_two_vendor` default-factory wires to `verify_claim_two_vendor_via_gateway`.
    # That picks up the configured gateway lazily; for an explicit gateway we re-wrap.
    from src.conflict.baml.templates import (  # noqa: PLC0415
        verify_claim_two_vendor_via_gateway,
    )
    agent.verify_two_vendor = lambda c, e: verify_claim_two_vendor_via_gateway(
        c, e, gateway=gateway,
    )

    correct = 0
    total_wall_ms = 0.0
    per_claim_summary: list[dict[str, Any]] = []

    for row in rows:
        claim = row["claim"]
        expected = row["expected_verdict"]
        start = time.perf_counter()
        try:
            result = agent.verify_claim(claim)
        except Exception as exc:  # noqa: BLE001 — surface every failure
            elapsed = time.perf_counter() - start
            print(
                f"  {row['id']}: FAIL exception={type(exc).__name__}: {exc} "
                f"({elapsed*1000:.0f}ms)",
            )
            per_claim_summary.append({
                "id": row["id"],
                "claim": claim,
                "expected": expected,
                "actual": "error",
                "error": str(exc),
                "ok": False,
                "wall_ms": elapsed * 1000,
            })
            continue
        elapsed = time.perf_counter() - start
        total_wall_ms += elapsed * 1000
        actual = result.verdict
        ok = actual == expected
        correct += int(ok)
        verdict_marker = "OK" if ok else "MISMATCH"
        print(
            f"  {row['id']}: {verdict_marker} expected={expected} actual={actual} "
            f"conf={result.confidence:.2f} cites={len(result.citations)} "
            f"low_conf={result.low_confidence} ({elapsed*1000:.0f}ms)",
        )
        per_claim_summary.append({
            "id": row["id"],
            "claim": claim,
            "expected": expected,
            "actual": actual,
            "confidence": result.confidence,
            "citations": result.citations[:3],
            "low_confidence": result.low_confidence,
            "ok": ok,
            "wall_ms": elapsed * 1000,
            "reason": result.reason,
        })

    total_cost = sum(c for _, c in cost_log)
    print()
    print("=== SUMMARY ===")
    print(f"resolved correctly: {correct}/5")
    print(f"total wall time:    {total_wall_ms:.0f}ms")
    print(f"total Tavily cost:  ${total_cost:.4f}")
    print(f"Tavily ops:         {len(cost_log)}")

    out_path = Path(".agent") / "reports" / "v1.5-fix-W1-8-tavily-live-results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "correct": correct,
        "total_claims": 5,
        "total_wall_ms": total_wall_ms,
        "total_tavily_cost_usd": total_cost,
        "tavily_ops": len(cost_log),
        "per_claim": per_claim_summary,
        "cost_log": [{"op": op, "cost": c} for op, c in cost_log],
    }, indent=2))
    print(f"raw results: {out_path}")

    return 0 if correct == 5 else 1


if __name__ == "__main__":
    sys.exit(main())
