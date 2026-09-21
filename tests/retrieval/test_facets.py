"""PV-5: faceted sub-topic detection, term distillation, and the counted kernel."""

from __future__ import annotations

import numpy as np

from src.retrieval.facets import facet_terms, is_facet_query
from src.retrieval.stance import classify_counted


def test_is_facet_query():
    assert is_facet_query("what are common dental school interview topics")
    assert is_facet_query("what sub-topics come up in interviews")
    assert is_facet_query("what do applicants discuss about NYU")
    assert not is_facet_query("how do applicants view NYU College of Dentistry")
    assert not is_facet_query("what are the cheapest dental schools")


def test_facet_terms_strips_markers():
    t = facet_terms("what are the common dental school interview-prep topics")
    assert "interview-prep" in t
    assert "topics" not in t and "common" not in t and "what" not in t
    assert "dental" not in t and "school" not in t   # corpus-universal words dropped


class _FakeStore:
    """2-D embedding space: 'behavioral' -> axis 0, everything else -> axis 1."""

    def embed_query(self, text):
        return (np.array([1.0, 0.0], dtype=np.float32) if "behavioral" in text.lower()
                else np.array([0.0, 1.0], dtype=np.float32))

    def vectors_for(self, ids):
        mat = np.array([[1.0, 0.0] if i % 2 == 0 else [0.0, 1.0]
                        for i in range(len(ids))], dtype=np.float32)
        return ids, mat


def test_classify_counted_counts_and_retains_ids():
    items = [{"label": "behavioral", "description": "behavioral questions"},
             {"label": "why-school", "description": "why this school"}]
    dist, classified, unclear, n = classify_counted(
        _FakeStore(), items, ["a", "b", "c", "d"], min_sim=0.5)
    assert classified == 4 and n == 4 and unclear == 0
    by = {d["label"]: d for d in dist}
    # even ids (a,c) -> axis0 -> behavioral; odd (b,d) -> axis1 -> why-school
    assert by["behavioral"]["n"] == 2 and set(by["behavioral"]["doc_ids"]) == {"a", "c"}
    assert by["why-school"]["n"] == 2 and set(by["why-school"]["doc_ids"]) == {"b", "d"}


def test_classify_counted_empty_vectors():
    class _Empty(_FakeStore):
        def vectors_for(self, ids):
            return [], np.zeros((0, 2), dtype=np.float32)

    dist, classified, unclear, n = classify_counted(
        _Empty(), [{"label": "x", "description": "y"}], ["a"], min_sim=0.5)
    assert classified == 0 and n == 0 and dist[0]["n"] == 0
