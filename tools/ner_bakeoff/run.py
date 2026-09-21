"""Run the ADR-022 NER bake-off: NuNER-Zero vs GLiNER2 vs rapidfuzz baseline.

  ./.venv/Scripts/python.exe -m tools.ner_bakeoff.run [--threshold 0.4] [--data-dir .agent/dj_l1c]

Span-level lenient matching (token Jaccard >= match-threshold): a gold span is
recalled if some predicted span overlaps it; a predicted span is a true positive
if it overlaps some gold span. Reports precision / recall / F1 (entity-detection,
type-agnostic) + type accuracy on matched pairs. The rapidfuzz baseline is the
production `Pass1MentionExtractor` over the same gold.
"""

from __future__ import annotations

import argparse
import re
import time
import warnings
from dataclasses import dataclass
from pathlib import Path

from tools.ner_bakeoff.gold import GOLD, LABELS, GoldItem

warnings.filterwarnings("ignore")

_MATCH_THRESHOLD = 0.5


def _tokens(text: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split())


def _overlap(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    # asymmetric containment OR Jaccard — credit "OMFS" inside a long gold span.
    return max(inter / len(ta | tb), inter / min(len(ta), len(tb)) * 0.8)


@dataclass
class Scored:
    name: str
    tp: int = 0
    fp: int = 0
    gold_total: int = 0
    recalled: int = 0
    type_correct: int = 0
    type_judged: int = 0
    seconds: float = 0.0

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        return self.recalled / self.gold_total if self.gold_total else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def type_acc(self) -> float:
        return self.type_correct / self.type_judged if self.type_judged else 0.0


def _score_predictions(
    name: str, predict: object, *, type_aware: bool, seconds: float,
) -> Scored:
    """predict: callable(GoldItem) -> list[(text, type|None)]."""
    s = Scored(name=name, seconds=seconds)
    for item in GOLD:
        preds = predict(item)  # type: ignore[operator]
        s.gold_total += len(item.spans)
        # recall: each gold span recalled if some pred overlaps it
        for g_text, g_type in item.spans:
            best = max((p for p in preds), default=None,
                       key=lambda p: _overlap(p[0], g_text))
            if best is not None and _overlap(best[0], g_text) >= _MATCH_THRESHOLD:
                s.recalled += 1
                if type_aware and best[1] is not None:
                    s.type_judged += 1
                    s.type_correct += int(best[1] == g_type)
        # precision: each pred is TP if it overlaps some gold span
        for p_text, _p_type in preds:
            if item.spans and max(
                (_overlap(p_text, g) for g, _ in item.spans), default=0.0,
            ) >= _MATCH_THRESHOLD:
                s.tp += 1
            else:
                s.fp += 1
    return s


def _gliner_predict(model_id: str, threshold: float) -> tuple[object, float]:
    from gliner import GLiNER  # noqa: PLC0415
    t0 = time.time()
    model = GLiNER.from_pretrained(model_id)
    load = time.time() - t0

    def predict(item: GoldItem) -> list[tuple[str, str]]:
        ents = model.predict_entities(item.text, LABELS, threshold=threshold)
        return [(e["text"], e["label"]) for e in ents]

    return predict, load


def _baseline_predict(data_dir: Path) -> object:
    from src.er.canonical_index import CanonicalIndex  # noqa: PLC0415
    from src.extraction.pass1_mention_extractor import Pass1MentionExtractor  # noqa: PLC0415
    idx = CanonicalIndex(sqlite_path=data_dir / "sqlite" / "store.db")
    ex = Pass1MentionExtractor(idx)

    def predict(item: GoldItem) -> list[tuple[str, None]]:
        # matched_alias is the surface span the matcher fired on.
        return [(m.matched_alias, None) for m in ex.extract(item.text)]

    return predict


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.4)
    ap.add_argument("--data-dir", default=".agent/dj_l1c")
    args = ap.parse_args()

    results: list[Scored] = []

    # baseline (fast, always available)
    t0 = time.time()
    base = _baseline_predict(Path(args.data_dir))
    results.append(_score_predictions(
        "rapidfuzz baseline (Pass1)", base, type_aware=False, seconds=time.time() - t0,
    ))

    for model_id in ("numind/NuNER_Zero", "urchade/gliner_multi-v2.1"):
        try:
            predict, load = _gliner_predict(model_id, args.threshold)
            results.append(_score_predictions(
                model_id, predict, type_aware=True, seconds=load,
            ))
        except Exception as ex:  # spike: report the failure and continue
            print(f"  {model_id} FAILED: {type(ex).__name__}: {str(ex)[:160]}")

    print(f"\nADR-022 NER bake-off — {len(GOLD)} gold items, "
          f"{sum(len(g.spans) for g in GOLD)} gold spans, threshold={args.threshold}\n")
    print(f"  {'method':30} {'P':>6} {'R':>6} {'F1':>6} {'type':>6} {'load(s)':>8}")
    for s in results:
        print(f"  {s.name:30} {s.precision:6.2f} {s.recall:6.2f} {s.f1:6.2f} "
              f"{s.type_acc:6.2f} {s.seconds:8.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
