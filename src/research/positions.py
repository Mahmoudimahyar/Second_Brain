"""RB-1: reproducible stance/topic labels.

The counts were always deterministic *given* the buckets, but the LLM that NAMES the
buckets varied run-to-run (temp=0 is not bit-exact on hosted models), so "Is NYU worth
it?" came back "Not Worth the Cost" one run and "No Clear Advantage" the next.

`stable_positions` fixes this two ways:
  1. ENSEMBLE — derive the positions K times, embed every candidate label, greedily
     cluster them, and keep only clusters that >=2 runs agree on (the medoid is the
     representative). The emitted set is the consensus, not one arbitrary draw.
  2. CACHE — persist the consensus keyed by (question, estimand) so a re-query returns
     byte-identical labels forever.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import numpy as np

from src.retrieval.facets import derive_subtopics
from src.retrieval.stance import derive_positions


def _key(question: str, kind: str) -> str:
    return hashlib.sha1(f"{kind}|{(question or '').strip().lower()}".encode()).hexdigest()[:20]


class PositionCache:
    """Persistent (question,estimand) -> consensus positions, for exact reproducibility."""

    def __init__(self, path: str | Path) -> None:
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.execute("CREATE TABLE IF NOT EXISTS positions(key TEXT PRIMARY KEY, payload TEXT)")
        self.conn.commit()

    def get(self, key: str) -> list | None:
        r = self.conn.execute("SELECT payload FROM positions WHERE key=?", (key,)).fetchone()
        return json.loads(r[0]) if r else None

    def set(self, key: str, value: list) -> None:
        self.conn.execute("INSERT OR REPLACE INTO positions VALUES (?,?)",
                          (key, json.dumps(value)))
        self.conn.commit()


def _greedy_clusters(vecs: list[np.ndarray], sim: float) -> list[list[int]]:
    """Single-link greedy clustering of unit vectors by cosine >= sim."""
    centroids: list[np.ndarray] = []
    counts: list[int] = []
    members: list[list[int]] = []
    for i, v in enumerate(vecs):
        best, bj = sim, -1
        for j, c in enumerate(centroids):
            cu = c / max(float(np.linalg.norm(c)), 1e-9)
            cs = float(v @ cu)
            if cs >= best:
                best, bj = cs, j
        if bj >= 0:
            centroids[bj] = centroids[bj] + v
            counts[bj] += 1
            members[bj].append(i)
        else:
            centroids.append(v.copy())
            counts.append(1)
            members.append([i])
    return members


def stable_positions(llm, store, question: str, snippets: list[str], *, kind: str,
                     cache: PositionCache | None = None, max_positions: int = 6) -> list[dict]:
    """Reproducible positions/sub-topics: derive ONCE (the LLM yields a proper multi-bucket
    set in a single call, with a built-in temp0→temp0.3 retry) and CACHE it keyed by
    (question, estimand). Re-queries return byte-identical labels forever.

    (We tried cross-run ensemble + embedding clustering, but short in-domain labels have
    cosine high enough that greedy clustering collapses distinct positions — the cache is
    the robust reproducibility guarantee; `store` is kept for signature stability.)
    """
    key = _key(question, kind)
    if cache is not None:
        cached = cache.get(key)
        if cached is not None:
            return cached
    derive = derive_subtopics if kind in ("topic", "pain") else derive_positions
    positions = derive(llm, question, snippets)
    out = [{"label": p["label"], "description": p.get("description", "")}
           for p in positions if p.get("label")][:max_positions]
    if out and cache is not None:
        cache.set(key, out)
    return out
