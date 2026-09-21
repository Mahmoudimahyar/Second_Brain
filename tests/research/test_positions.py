"""RB-1: reproducible label derivation — cache + ensemble canonicalization."""

from __future__ import annotations

import numpy as np

from src.research.positions import PositionCache, _greedy_clusters, _key, stable_positions


def test_key_deterministic():
    assert _key("Is NYU worth it?", "stance") == _key("is nyu worth it? ", "stance")
    assert _key("q", "stance") != _key("q", "topic")


def test_cache_roundtrip():
    c = PositionCache(":memory:")
    assert c.get("k") is None
    c.set("k", [{"label": "A"}])
    assert c.get("k") == [{"label": "A"}]


def test_greedy_clusters():
    v = [np.array([1.0, 0.0]), np.array([0.99, 0.01]), np.array([0.0, 1.0])]
    v = [x / np.linalg.norm(x) for x in v]
    clusters = _greedy_clusters(v, 0.9)
    assert len(clusters) == 2                       # first two merge, third separate
    assert sorted(len(c) for c in clusters) == [1, 2]


class _LLM:
    def complete(self, prompt, schema=None, temperature=0.0):
        class _R:
            raw_text = ('[{"label":"Cost","description":"too expensive"},'
                        '{"label":"Quality","description":"good program"}]')
        return _R()


class _Store:
    def embed_query(self, text):
        t = text.lower()
        if "cost" in t or "expensive" in t:
            return np.array([1.0, 0.0, 0.0], dtype=np.float32)
        if "quality" in t or "program" in t:
            return np.array([0.0, 1.0, 0.0], dtype=np.float32)
        return np.array([0.0, 0.0, 1.0], dtype=np.float32)


def test_stable_positions_derive_and_cache():
    cache = PositionCache(":memory:")
    pos = stable_positions(_LLM(), _Store(), "Is it worth it?", ["snippet"],
                           kind="stance", cache=cache)
    assert {p["label"] for p in pos} == {"Cost", "Quality"}
    # second call returns the cached set even if the LLM would now differ -> reproducible
    again = stable_positions(None, _Store(), "Is it worth it?", ["x"], kind="stance", cache=cache)
    assert again == pos
