"""Alias-resolution eval harness per slice AC #3 (F1 ≥ 0.92 on 200-mention gold set).

Run via `python -m evals.alias_resolution` against a populated SQLite alias table.
Computes precision/recall/F1 against `evals/gold/alias_mentions.jsonl`.

Gold-set entry shape (JSONL):
  {"text": "I got into NYU!", "expected_canonical_id": "school:new_york_university", "note": "..."}
  {"text": "I love my morning coffee.", "expected_canonical_id": null, "note": "no-match"}
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from src.er.canonical_index import CanonicalIndex
from src.extraction.pass1_mention_extractor import Pass1MentionExtractor


@dataclass(frozen=True)
class GoldMention:
    text: str
    expected_canonical_id: str | None
    note: str = ""


@dataclass(frozen=True)
class EvalResult:
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float
    recall: float
    f1: float
    misses: list[tuple[GoldMention, list[str]]]   # (gold, predicted_canonical_ids)

    def passes_threshold(self, threshold: float = 0.92) -> bool:
        return self.f1 >= threshold


def load_gold(path: Path) -> list[GoldMention]:
    out: list[GoldMention] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        obj = json.loads(line)
        out.append(GoldMention(
            text=str(obj["text"]),
            expected_canonical_id=obj.get("expected_canonical_id"),
            note=str(obj.get("note") or ""),
        ))
    return out


def evaluate(
    gold: list[GoldMention],
    matcher: Pass1MentionExtractor,
) -> EvalResult:
    tp = fp = fn = tn = 0
    misses: list[tuple[GoldMention, list[str]]] = []

    for g in gold:
        predictions = matcher.extract(g.text)
        # We treat the auto-accept set as the matcher's "decision".
        accepted = [m for m in predictions if not m.needs_review]
        predicted_ids = [m.canonical_id for m in accepted]

        if g.expected_canonical_id is None:
            # Expected no match
            if not predicted_ids:
                tn += 1
            else:
                fp += 1
                misses.append((g, predicted_ids))
        elif g.expected_canonical_id in predicted_ids:
            tp += 1
        elif not predicted_ids:
            fn += 1
            misses.append((g, []))
        else:
            # Got a prediction but it's the wrong one — count as both FP + FN
            # (precision and recall both drop).
            fp += 1
            fn += 1
            misses.append((g, predicted_ids))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return EvalResult(
        tp=tp, fp=fp, fn=fn, tn=tn,
        precision=precision, recall=recall, f1=f1, misses=misses,
    )


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    sqlite_path = Path(argv[0]) if argv else Path("data/sqlite/store.db")
    gold_path = Path(argv[1]) if len(argv) > 1 else (
        Path(__file__).parent / "gold" / "alias_mentions.jsonl"
    )

    if not gold_path.is_file():
        print(f"[err] gold file not found: {gold_path}")
        return 2
    if not sqlite_path.is_file():
        print(f"[err] SQLite alias DB not found: {sqlite_path}")
        return 2

    idx = CanonicalIndex(sqlite_path=sqlite_path)
    matcher = Pass1MentionExtractor(idx)
    gold = load_gold(gold_path)

    result = evaluate(gold, matcher)
    print(f"gold mentions:   {len(gold)}")
    print(f"alias universe:  {idx.alias_count()}")
    print()
    print(f"true positives:  {result.tp}")
    print(f"false positives: {result.fp}")
    print(f"false negatives: {result.fn}")
    print(f"true negatives:  {result.tn}")
    print()
    print(f"precision: {result.precision:.3f}")
    print(f"recall:    {result.recall:.3f}")
    print(f"F1:        {result.f1:.3f}")
    print()
    if result.misses:
        print("--- mismatches ---")
        for g, predicted in result.misses[:20]:
            exp = g.expected_canonical_id or "<none>"
            got = predicted or ["<none>"]
            print(f"  text={g.text[:60]!r}")
            print(f"    expected={exp}  got={got}")
            if g.note:
                print(f"    note: {g.note}")

    threshold = 0.92
    if result.f1 >= threshold:
        print(f"\n[ok] F1 {result.f1:.3f} >= {threshold} threshold (AC #3 PASS)")
        return 0
    print(f"\n[fail] F1 {result.f1:.3f} < {threshold} threshold")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
