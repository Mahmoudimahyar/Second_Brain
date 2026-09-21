"""MH-2: data-driven k-means topic clustering."""

from __future__ import annotations

import numpy as np

from src.research.clustering import _kmeans_spherical, kmeans_topics, top_cluster_fraction


def _sphere(blocks: list[tuple[list[float], int]]) -> np.ndarray:
    rows = []
    for direction, count in blocks:
        rows.append(np.tile(direction, (count, 1)))
    mat = np.vstack(rows).astype(np.float32)
    return mat / np.linalg.norm(mat, axis=1, keepdims=True)


def test_kmeans_spherical_separates():
    mat = _sphere([([1.0, 0, 0], 50), ([0, 1.0, 0], 50)])
    labels, _ = _kmeans_spherical(mat, 2, seed=0)
    assert len(set(labels[:50].tolist())) == 1 and len(set(labels[50:].tolist())) == 1
    assert labels[0] != labels[50]


class _Store:
    def __init__(self, mat, ids):
        self.mat, self.ids = mat, ids

    def vectors_for(self, doc_ids):
        return self.ids, self.mat


def test_top_cluster_fraction_imbalanced():
    mat = _sphere([([1.0, 0, 0], 80), ([0, 1.0, 0], 20)])
    ids = [str(i) for i in range(100)]
    f = top_cluster_fraction(_Store(mat, ids), ids, k=2, seed=0)
    assert 0.74 <= f <= 0.86           # ~0.80 largest-cluster share


class _LLM:
    def complete(self, prompt, schema=None, temperature=0.0):
        class _R:
            raw_text = '[{"label":"Alpha","description":"x"},{"label":"Beta","description":"y"}]'
        return _R()


def test_kmeans_topics_balanced_no_catchall():
    mat = _sphere([([1.0, 0, 0], 50), ([0, 1.0, 0], 50)])
    ids = [str(i) for i in range(100)]
    out = kmeans_topics(_Store(mat, ids), _LLM(), ids, k=2,
                        snippet_fn=lambda xs: {x: "text" for x in xs}, min_cluster=5)
    assert len(out) == 2
    assert {o["label"] for o in out} == {"Alpha", "Beta"}
    assert sum(o["n"] for o in out) == 100
    assert max(o["fraction"] for o in out) <= 0.55     # balanced, no catch-all
