"""Tests for `src.embeddings.hash_embedder.HashEmbeddingService`."""

from __future__ import annotations

import math

import pytest

from src.embeddings.hash_embedder import HashEmbeddingService, cosine_similarity


def test_embed_returns_correct_dim() -> None:
    svc = HashEmbeddingService(dim=384)
    e = svc.embed("hello world")
    assert len(e.vector) == 384
    assert e.model == "hash-stub-v1"


def test_embed_is_deterministic() -> None:
    svc = HashEmbeddingService(dim=384)
    a = svc.embed("the same text")
    b = svc.embed("the same text")
    assert a.vector == b.vector


def test_different_texts_produce_different_vectors() -> None:
    svc = HashEmbeddingService(dim=384)
    a = svc.embed("alpha")
    b = svc.embed("beta")
    assert a.vector != b.vector


def test_l2_normalized() -> None:
    svc = HashEmbeddingService(dim=384)
    e = svc.embed("normalize me")
    norm = math.sqrt(sum(v * v for v in e.vector))
    assert norm == pytest.approx(1.0, abs=1e-6)


def test_cosine_similarity_self_is_one() -> None:
    svc = HashEmbeddingService(dim=384)
    e = svc.embed("foo")
    assert cosine_similarity(e, e) == pytest.approx(1.0, abs=1e-6)


def test_batch_returns_one_embedding_per_input() -> None:
    svc = HashEmbeddingService(dim=384)
    out = svc.embed_batch(["a", "b", "c"])
    assert len(out) == 3
    assert out[0].text == "a"
    assert out[2].text == "c"


def test_dim_validation_rejects_non_multiple_of_8() -> None:
    with pytest.raises(ValueError):
        HashEmbeddingService(dim=37)
    with pytest.raises(ValueError):
        HashEmbeddingService(dim=0)


def test_embed_normalizes_whitespace_to_consistent_vector() -> None:
    svc = HashEmbeddingService(dim=384)
    a = svc.embed("hello")
    b = svc.embed("  hello  ")
    assert a.vector == b.vector


def test_smaller_dim_works() -> None:
    svc = HashEmbeddingService(dim=16)
    e = svc.embed("x")
    assert len(e.vector) == 16
