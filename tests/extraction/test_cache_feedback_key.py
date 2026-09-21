"""Tests for V1.5b cache-key extension — FR-1.5b-7.5.

The Pass-4 cache key must include `feedback_context_hash` so that a feedback
decision change invalidates only the affected template's cache entries.
"""

from __future__ import annotations

from src.extraction.cache import ExtractionCache


def _kwargs() -> dict[str, str]:
    return {
        "thread_content": "post body",
        "prompt_id": "extract_sentiment",
        "prompt_version": "v1",
        "schema_hash": "abc",
        "model_id": "haiku-4.5",
        "model_version": "20251022",
    }


def test_v1_callers_unaffected() -> None:
    """V1 callers that don't pass `feedback_context_hash` get the same
    cache key shape as before."""
    base = _kwargs()
    k1 = ExtractionCache.make_key(**base)
    k2 = ExtractionCache.make_key(**base)
    assert k1 == k2
    assert k1.startswith("cache:")


def test_different_feedback_hash_yields_different_key() -> None:
    """V1.5b: changing the feedback context invalidates the cache entry."""
    k1 = ExtractionCache.make_key(
        **_kwargs(), feedback_context_hash="hash_a",
    )
    k2 = ExtractionCache.make_key(
        **_kwargs(), feedback_context_hash="hash_b",
    )
    assert k1 != k2


def test_no_feedback_vs_empty_feedback_differ() -> None:
    """An explicit empty hash and `None` produce different keys (they
    semantically mean different things: no feedback vs feedback exists
    but happens to be empty)."""
    k_none = ExtractionCache.make_key(**_kwargs())
    k_empty = ExtractionCache.make_key(
        **_kwargs(), feedback_context_hash="",
    )
    assert k_none != k_empty


def test_same_feedback_hash_yields_same_key() -> None:
    k1 = ExtractionCache.make_key(
        **_kwargs(), feedback_context_hash="stable_hash_xyz",
    )
    k2 = ExtractionCache.make_key(
        **_kwargs(), feedback_context_hash="stable_hash_xyz",
    )
    assert k1 == k2


def test_per_template_isolation_via_prompt_id() -> None:
    """Two different templates with the same feedback context produce
    different keys (FR-1.5b-7.5: cache invalidation is per-template)."""
    base = _kwargs()
    k1 = ExtractionCache.make_key(
        **{**base, "prompt_id": "extract_sentiment"},
        feedback_context_hash="same_hash",
    )
    k2 = ExtractionCache.make_key(
        **{**base, "prompt_id": "extract_interview_q"},
        feedback_context_hash="same_hash",
    )
    assert k1 != k2
