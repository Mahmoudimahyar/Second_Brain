"""Blocking-recall A/B for ER embedders (ADR-022 / WP4.2, GAP-044 gold).

Blocking = the embedding step that retrieves candidate canonical entities for a
mention before the reranker. For each gold *positive* mention this measures
whether the correct canonical entity is in the embedder's top-k by cosine, and
compares two `EmbeddingService` implementations (BGE-small vs Qwen3-0.6B).

Decision (ADR-022): adopt Qwen3 only if its blocking recall >= BGE's.

Run: `python -m evals.blocking_recall <sqlite> <gold.jsonl>`.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

from src.embeddings.api import Embedding, EmbeddingService
from src.er.canonical_index import CanonicalIndex

_KS = (1, 5, 10)


def _canonical_names(aliases: dict[str, str]) -> dict[str, str]:
    best: dict[str, str] = {}
    for alias, cid in aliases.items():
        if cid not in best or len(alias) > len(best[cid]):
            best[cid] = alias
    return best


def _load_positives(gold_path: Path) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for raw in gold_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        obj = json.loads(line)
        cid = obj.get("expected_canonical_id")
        if cid:
            out.append((str(obj["text"]), str(cid)))
    return out


def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


@dataclass(frozen=True)
class RecallResult:
    embedder: str
    n: int
    recall_at: dict[int, float]


def measure(
    embedder: EmbeddingService,
    names: dict[str, str],
    positives: list[tuple[str, str]],
    ks: tuple[int, ...] = _KS,
) -> RecallResult:
    cids = list(names.keys())
    name_vecs: list[Embedding] = embedder.embed_batch([names[c] for c in cids])
    vectors = [e.vector for e in name_vecs]

    hits = dict.fromkeys(ks, 0)
    for text, expected in positives:
        q = embedder.embed(text).vector
        sims = sorted(
            ((_cosine(q, vectors[i]), cids[i]) for i in range(len(cids))),
            reverse=True,
        )
        ranked = [cid for _, cid in sims]
        for k in ks:
            if expected in ranked[:k]:
                hits[k] += 1
    n = len(positives)
    return RecallResult(
        embedder=embedder.model, n=n,
        recall_at={k: (hits[k] / n if n else 0.0) for k in ks},
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="evals.blocking_recall")
    p.add_argument("sqlite", type=Path)
    p.add_argument("gold", type=Path)
    args = p.parse_args(argv)

    idx = CanonicalIndex(sqlite_path=args.sqlite)
    names = _canonical_names(idx.aliases())
    positives = _load_positives(args.gold)
    if not positives:
        print("[err] no positive gold mentions found")
        return 2

    from src.embeddings.bge_embedder import BGEEmbeddingService  # noqa: PLC0415
    from src.embeddings.qwen_embedder import QwenEmbeddingService  # noqa: PLC0415

    bge = measure(BGEEmbeddingService(), names, positives)
    qwen = measure(QwenEmbeddingService(), names, positives)

    print(f"canonical entities: {len(names)}   positive mentions: {bge.n}\n")
    for r in (bge, qwen):
        line = "  ".join(f"R@{k}={r.recall_at[k]:.3f}" for k in _KS)
        print(f"  {r.embedder:32} {line}")

    print()
    if qwen.recall_at[5] >= bge.recall_at[5]:
        print(f"[ship] Qwen3 R@5 {qwen.recall_at[5]:.3f} >= BGE {bge.recall_at[5]:.3f} - adopt Qwen3 (ADR-022)")
        return 0
    print(f"[hold] Qwen3 R@5 {qwen.recall_at[5]:.3f} < BGE {bge.recall_at[5]:.3f} - keep BGE")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
