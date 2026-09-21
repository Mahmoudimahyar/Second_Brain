"""By-id embedding lookup + cosine scoring over the post/comment shards.

Enables the Evidence Dossier relevance filter (ED-3): given a candidate set of
doc_ids (e.g. the 154K SDN posts the graph linked to a school), score each by
cosine vs the question embedding and keep those above a floor. This is what turns
the broad-recall population into the honest "N relevant" set.

Coverage (verified 2026-06-18): `posts_bge` = 503,486 sdn_post + 373,702 reddit_post;
`comments_bge` = 1,953,599 reddit_comment. So graph (SDN), reddit-post and
reddit-comment candidates can all be scored. Docs with no vector (≈no text) score
None and are handled by the caller (keyword fallback or drop).

Runs where the shards live (EC2 VM / bundle). Vectors are L2-normalised at write
time, so cosine == dot product. Lock-free: reads .npy + .ids.txt, never the graph.
"""

from __future__ import annotations

import glob
import os
from collections import defaultdict

import numpy as np


class EmbeddingStore:
    def __init__(self, emb_dir: str, *, embedder=None) -> None:
        self._shards: list[tuple[np.ndarray, list[str]]] = []
        self._index: dict[str, tuple[int, int]] = {}  # doc_id -> (shard, row)
        for pattern in ("posts_bge.*.npy", "comments_bge.*.npy"):
            for vec_path in sorted(glob.glob(os.path.join(emb_dir, pattern))):
                ids_path = vec_path[: -len(".npy")] + ".ids.txt"
                if not os.path.exists(ids_path):
                    continue
                vecs = np.load(vec_path, mmap_mode="r")
                with open(ids_path, encoding="utf-8") as fh:
                    ids = fh.read().splitlines()
                if len(ids) != vecs.shape[0]:
                    continue
                si = len(self._shards)
                self._shards.append((vecs, ids))
                for ri, did in enumerate(ids):
                    self._index[did] = (si, ri)
        self._embedder = embedder

    @property
    def size(self) -> int:
        return len(self._index)

    def has(self, doc_id: str) -> bool:
        return doc_id in self._index

    def embed_query(self, query: str) -> np.ndarray:
        if self._embedder is None:
            from src.embeddings.bge_embedder import BGEEmbeddingService  # noqa: PLC0415

            self._embedder = BGEEmbeddingService(device="cpu")
        v = np.asarray(self._embedder.embed_batch([query])[0].vector, dtype=np.float32)
        return v / max(float(np.linalg.norm(v)), 1e-9)

    def vectors_for(self, doc_ids: list[str]) -> tuple[list[str], np.ndarray]:
        """Return (found_ids, matrix) of the L2-normalised vectors for known doc_ids.

        Used by stance classification (ED-5): cosine of each relevant doc vs the
        position prototypes is one matmul once the vectors are gathered.
        """
        by_shard: dict[int, list[tuple[int, str]]] = defaultdict(list)
        for did in doc_ids:
            loc = self._index.get(did)
            if loc is not None:
                by_shard[loc[0]].append((loc[1], did))
        ids: list[str] = []
        mats: list[np.ndarray] = []
        for si, items in by_shard.items():
            vecs, _ = self._shards[si]
            rows = [r for r, _ in items]
            mats.append(np.asarray(vecs[rows], dtype=np.float32))
            ids.extend(did for _, did in items)
        if not mats:
            return [], np.zeros((0, 384), dtype=np.float32)
        return ids, np.vstack(mats)

    def score(self, doc_ids: list[str], query_vec: np.ndarray) -> dict[str, float]:
        """Cosine of each known doc_id vs `query_vec` (normalised). Unknown ids omitted.

        Groups by shard so each shard's rows are gathered + dotted in one vectorised
        op — no per-id Python matmul.
        """
        by_shard: dict[int, list[tuple[int, str]]] = defaultdict(list)
        for did in doc_ids:
            loc = self._index.get(did)
            if loc is not None:
                by_shard[loc[0]].append((loc[1], did))

        out: dict[str, float] = {}
        for si, items in by_shard.items():
            vecs, _ = self._shards[si]
            rows = [r for r, _ in items]
            sub = np.asarray(vecs[rows], dtype=np.float32)  # (len, 384) copy from mmap
            sims = sub @ query_vec
            for (_, did), s in zip(items, sims):
                out[did] = float(s)
        return out

    def filter_by_floor(
        self,
        doc_ids: list[str],
        query: str | np.ndarray,
        *,
        floor: float = 0.35,
        band: float = 0.05,
    ) -> dict[str, list]:
        """Partition candidates by cosine vs the question.

        Returns {"keep": [(id, score)...], "borderline": [...], "drop": [...],
        "no_vector": [ids]} — 'borderline' is the [floor-band, floor) zone handed to
        the LLM relevance gate (ED-3 stage C). Sorted by score desc within each band.
        """
        q = self.embed_query(query) if isinstance(query, str) else query
        scores = self.score(doc_ids, q)
        keep: list[tuple[str, float]] = []
        borderline: list[tuple[str, float]] = []
        drop: list[tuple[str, float]] = []
        no_vec: list[str] = []
        for did in doc_ids:
            s = scores.get(did)
            if s is None:
                no_vec.append(did)
            elif s >= floor:
                keep.append((did, s))
            elif s >= floor - band:
                borderline.append((did, s))
            else:
                drop.append((did, s))
        keep.sort(key=lambda x: -x[1])
        borderline.sort(key=lambda x: -x[1])
        drop.sort(key=lambda x: -x[1])
        return {"keep": keep, "borderline": borderline, "drop": drop, "no_vector": no_vec}
