"""Tests for `src.extraction.cache.ExtractionCache` (FR-2.4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.extraction.cache import CacheEntry, ExtractionCache


def _cache(tmp_path: Path) -> ExtractionCache:
    return ExtractionCache(sqlite_path=tmp_path / "cache.db")


def test_cache_starts_empty(tmp_path: Path) -> None:
    c = _cache(tmp_path)
    assert c.size() == 0


def test_make_key_is_deterministic() -> None:
    args = dict(
        thread_content="hello world",
        prompt_id="sentiment.v1", prompt_version="1.0",
        schema_hash="sha", model_id="haiku-4.5", model_version="2026",
    )
    k1 = ExtractionCache.make_key(**args)  # type: ignore[arg-type]
    k2 = ExtractionCache.make_key(**args)  # type: ignore[arg-type]
    assert k1 == k2
    assert k1.startswith("cache:")


def test_make_key_changes_on_any_input_change() -> None:
    base = dict(
        thread_content="x", prompt_id="p", prompt_version="1",
        schema_hash="s", model_id="m", model_version="v",
    )
    base_key = ExtractionCache.make_key(**base)  # type: ignore[arg-type]
    for field, value in base.items():
        mutated = {**base, field: value + "!"}
        assert ExtractionCache.make_key(**mutated) != base_key  # type: ignore[arg-type]


def test_put_then_get_round_trips(tmp_path: Path) -> None:
    c = _cache(tmp_path)
    entry = CacheEntry(
        cache_key="cache:abc",
        output_json='{"verdict":"positive"}',
        vendor="anthropic", model="haiku-4.5", model_version="2026",
        input_tokens=100, output_tokens=20, cached_input_tokens=80,
        cost_usd=0.001,
    )
    c.put(entry)

    fetched = c.get("cache:abc")
    assert fetched is not None
    assert fetched.output_json == '{"verdict":"positive"}'
    assert fetched.vendor == "anthropic"
    assert fetched.cost_usd == pytest.approx(0.001)
    assert c.size() == 1


def test_get_returns_none_for_missing_key(tmp_path: Path) -> None:
    assert _cache(tmp_path).get("cache:none") is None


def test_put_output_serializes_dict(tmp_path: Path) -> None:
    c = _cache(tmp_path)
    c.put_output(
        "cache:dict",
        {"verdict": "negative", "spans": [1, 2, 3]},
        vendor="gemini", model="flash-lite",
    )

    fetched = c.get("cache:dict")
    assert fetched is not None
    assert '"verdict": "negative"' in fetched.output_json


def test_put_is_idempotent_on_same_key(tmp_path: Path) -> None:
    c = _cache(tmp_path)
    c.put_output("cache:x", {"v": 1})
    c.put_output("cache:x", {"v": 2})
    assert c.size() == 1
    fetched = c.get("cache:x")
    assert fetched is not None
    assert '"v": 2' in fetched.output_json


def test_warm_sweep_simulates_high_hit_rate(tmp_path: Path) -> None:
    """Simulate NFR-3: warm-sweep cache hit >= 80%."""

    c = _cache(tmp_path)
    keys = [
        ExtractionCache.make_key(
            thread_content=f"thread {i}",
            prompt_id="p", prompt_version="1",
            schema_hash="s", model_id="m", model_version="v",
        )
        for i in range(100)
    ]
    # Cold sweep — all miss.
    cold_hits = sum(1 for k in keys if c.get(k) is not None)
    for k in keys:
        c.put_output(k, {"x": 1})
    # Warm sweep — all hit.
    warm_hits = sum(1 for k in keys if c.get(k) is not None)

    assert cold_hits == 0
    assert warm_hits == 100
    assert c.hit_rate(100, warm_hits) >= 0.80
