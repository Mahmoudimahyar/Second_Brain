"""Interview-question extraction eval harness (Pass 4 interview_q).

Run: `python -m evals.interview_q <sqlite_path>`. Loads
`evals/gold/interview_q.jsonl`, runs each text through `extract_interview_questions()`,
and reports precision/recall on questions harvested.

Gold-set entry shape:
  {"text": "...", "expected_questions": ["Why our school?", "Describe a failure"],
   "expected_count": 2, "note": "..."}
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from src.extraction.cache import ExtractionCache
from src.extraction.pass4_runners import extract_interview_questions
from src.gateway import default_gateway


@dataclass(frozen=True)
class GoldInterviewQ:
    text: str
    expected_questions: list[str]
    note: str = ""

    @property
    def expected_count(self) -> int:
        return len(self.expected_questions)


@dataclass(frozen=True)
class InterviewQEvalResult:
    total_inputs: int
    expected_q_total: int
    predicted_q_total: int
    matched_q: int           # fuzzy substring match
    precision: float
    recall: float
    f1: float
    mismatches: list[tuple[GoldInterviewQ, list[str]]]
    cost_usd: float

    def passes_threshold(self, threshold: float = 0.75) -> bool:
        return self.f1 >= threshold


def load_gold(path: Path) -> list[GoldInterviewQ]:
    out: list[GoldInterviewQ] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        obj = json.loads(line)
        out.append(GoldInterviewQ(
            text=str(obj["text"]),
            expected_questions=list(obj.get("expected_questions", [])),
            note=str(obj.get("note") or ""),
        ))
    return out


def _fuzzy_question_match(predicted: str, expected: str) -> bool:
    """Loose substring + token-overlap check. Good enough for V1 eval."""

    p = predicted.lower()
    e = expected.lower()
    if e in p or p in e:
        return True
    p_tokens = set(p.split())
    e_tokens = set(e.split())
    if not e_tokens:
        return False
    overlap = len(p_tokens & e_tokens) / len(e_tokens)
    return overlap >= 0.6


def evaluate(
    gold: list[GoldInterviewQ], *, sqlite_path: Path,
) -> InterviewQEvalResult:
    cache = ExtractionCache(sqlite_path=sqlite_path)
    gw = default_gateway()

    expected_q_total = sum(g.expected_count for g in gold)
    predicted_q_total = 0
    matched = 0
    mismatches: list[tuple[GoldInterviewQ, list[str]]] = []
    cost = 0.0

    for g in gold:
        outcome = extract_interview_questions(g.text, gateway=gw, cache=cache)
        cost += outcome.cost_usd
        predictions: list[str] = []
        if outcome.parsed is not None:
            predictions = [q.text for q in outcome.parsed.questions]  # type: ignore[attr-defined]
        predicted_q_total += len(predictions)

        for expected_q in g.expected_questions:
            if any(_fuzzy_question_match(p, expected_q) for p in predictions):
                matched += 1
        if (g.expected_questions and not predictions) or (
            not g.expected_questions and predictions
        ):
            mismatches.append((g, predictions))

    precision = matched / predicted_q_total if predicted_q_total > 0 else 0.0
    recall = matched / expected_q_total if expected_q_total > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0 else 0.0
    )
    return InterviewQEvalResult(
        total_inputs=len(gold),
        expected_q_total=expected_q_total,
        predicted_q_total=predicted_q_total,
        matched_q=matched,
        precision=precision, recall=recall, f1=f1,
        mismatches=mismatches, cost_usd=cost,
    )


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    sqlite_path = Path(argv[0]) if argv else Path("data/sqlite/store.db")
    gold_path = Path(argv[1]) if len(argv) > 1 else (
        Path(__file__).parent / "gold" / "interview_q.jsonl"
    )
    if not gold_path.is_file():
        print(f"[err] gold file not found: {gold_path}")
        return 2

    gold = load_gold(gold_path)
    if not gold:
        print(f"[warn] empty gold set at {gold_path}")
        return 0

    result = evaluate(gold, sqlite_path=sqlite_path)

    print(f"gold entries:           {result.total_inputs}")
    print(f"expected question total: {result.expected_q_total}")
    print(f"predicted question total: {result.predicted_q_total}")
    print(f"matched (fuzzy):         {result.matched_q}")
    print()
    print(f"precision: {result.precision:.3f}")
    print(f"recall:    {result.recall:.3f}")
    print(f"F1:        {result.f1:.3f}")
    print(f"total cost: ${result.cost_usd:.4f}")

    if result.mismatches:
        print()
        print("--- mismatches ---")
        for g, predicted in result.mismatches[:10]:
            print(f"  text={g.text[:60]!r}")
            print(f"    expected_q={g.expected_questions}")
            print(f"    predicted_q={predicted}")

    threshold = 0.75
    if result.f1 >= threshold:
        print(f"\n[ok] F1 {result.f1:.3f} >= {threshold} (V1 threshold PASS)")
        return 0
    print(f"\n[fail] F1 {result.f1:.3f} < {threshold}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
