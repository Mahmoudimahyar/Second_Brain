"""Sentiment-extraction eval harness (Pass 4 sentiment).

Run: `python -m evals.sentiment <sqlite_path>`. Loads `evals/gold/sentiment.jsonl`,
sends each entry through `extract_sentiment()` via `default_gateway()`, compares
the predicted verdict to the gold label, and reports accuracy + per-verdict F1.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from src.extraction.cache import ExtractionCache
from src.extraction.pass4_runners import extract_sentiment
from src.gateway import default_gateway


@dataclass(frozen=True)
class GoldSentiment:
    text: str
    expected_verdict: str   # positive / negative / neutral / mixed
    expected_target_entities: list[str]
    note: str = ""


@dataclass(frozen=True)
class SentimentEvalResult:
    total: int
    correct: int
    accuracy: float
    by_verdict: dict[str, dict[str, int]]   # {verdict: {tp, fp, fn}}
    mismatches: list[tuple[GoldSentiment, str | None]]
    cost_usd: float

    def passes_threshold(self, threshold: float = 0.80) -> bool:
        return self.accuracy >= threshold


def load_gold(path: Path) -> list[GoldSentiment]:
    out: list[GoldSentiment] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        obj = json.loads(line)
        out.append(GoldSentiment(
            text=str(obj["text"]),
            expected_verdict=str(obj["expected_verdict"]),
            expected_target_entities=list(obj.get("expected_target_entities", [])),
            note=str(obj.get("note") or ""),
        ))
    return out


def evaluate(
    gold: list[GoldSentiment], *, sqlite_path: Path,
) -> SentimentEvalResult:
    cache = ExtractionCache(sqlite_path=sqlite_path)
    gw = default_gateway()

    correct = 0
    by_verdict: dict[str, dict[str, int]] = {}
    mismatches: list[tuple[GoldSentiment, str | None]] = []
    cost = 0.0

    for g in gold:
        outcome = extract_sentiment(g.text, gateway=gw, cache=cache)
        cost += outcome.cost_usd
        predicted = getattr(outcome.parsed, "verdict", None) if outcome.parsed else None

        expected_bucket = by_verdict.setdefault(
            g.expected_verdict, {"tp": 0, "fp": 0, "fn": 0},
        )
        predicted_bucket = by_verdict.setdefault(
            predicted or "<none>", {"tp": 0, "fp": 0, "fn": 0},
        )
        if predicted == g.expected_verdict:
            correct += 1
            expected_bucket["tp"] += 1
        else:
            expected_bucket["fn"] += 1
            if predicted is not None:
                predicted_bucket["fp"] += 1
            mismatches.append((g, predicted))

    accuracy = correct / len(gold) if gold else 0.0
    return SentimentEvalResult(
        total=len(gold), correct=correct, accuracy=accuracy,
        by_verdict=by_verdict, mismatches=mismatches, cost_usd=cost,
    )


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    sqlite_path = Path(argv[0]) if argv else Path("data/sqlite/store.db")
    gold_path = Path(argv[1]) if len(argv) > 1 else (
        Path(__file__).parent / "gold" / "sentiment.jsonl"
    )
    if not gold_path.is_file():
        print(f"[err] gold file not found: {gold_path}")
        return 2

    gold = load_gold(gold_path)
    if not gold:
        print(f"[warn] empty gold set at {gold_path}")
        return 0

    result = evaluate(gold, sqlite_path=sqlite_path)

    print(f"gold entries:   {result.total}")
    print(f"correct:        {result.correct}")
    print(f"accuracy:       {result.accuracy:.3f}")
    print(f"total cost USD: ${result.cost_usd:.4f}")
    print()
    print("--- per-verdict counts ---")
    for verdict in sorted(result.by_verdict):
        b = result.by_verdict[verdict]
        precision = b["tp"] / (b["tp"] + b["fp"]) if (b["tp"] + b["fp"]) > 0 else 0.0
        recall = b["tp"] / (b["tp"] + b["fn"]) if (b["tp"] + b["fn"]) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0 else 0.0
        )
        print(
            f"  {verdict:<10s} tp={b['tp']} fp={b['fp']} fn={b['fn']} "
            f"P={precision:.2f} R={recall:.2f} F1={f1:.2f}",
        )
    if result.mismatches:
        print()
        print("--- mismatches ---")
        verdicts = Counter(predicted for _, predicted in result.mismatches)
        print(f"  predicted-verdict distribution: {dict(verdicts)}")
        for g, predicted in result.mismatches[:10]:
            print(
                f"  text={g.text[:60]!r} expected={g.expected_verdict} "
                f"got={predicted}",
            )

    threshold = 0.80
    if result.accuracy >= threshold:
        print(f"\n[ok] accuracy {result.accuracy:.3f} >= {threshold} (V1 threshold PASS)")
        return 0
    print(f"\n[fail] accuracy {result.accuracy:.3f} < {threshold}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
