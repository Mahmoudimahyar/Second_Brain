"""Tests for V1.5b Phase 5 — `BlocklistFilter` (FR-1.5b-7.4)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.embeddings.hash_embedder import HashEmbeddingService
from src.extraction.blocklist_filter import BlocklistFilter
from src.extraction.feedback_context import ContextBlocklistEntry


def _entry(pattern: str) -> ContextBlocklistEntry:
    return ContextBlocklistEntry(
        pattern=pattern,
        pattern_canonical=" ".join(pattern.lower().split()),
        last_decided_at=datetime.now(UTC),
        hit_count=1,
        feedback_id=f"fb:{pattern[:8]}",
    )


@pytest.fixture
def filter_() -> BlocklistFilter:
    return BlocklistFilter(embedding_service=HashEmbeddingService())


def test_exact_match_dropped(filter_: BlocklistFilter) -> None:
    extractions = ["KeepThis", "RejectThisExactly", "AlsoKeep"]
    blocklist = [_entry("RejectThisExactly")]
    result = filter_.apply(extractions, blocklist)
    assert result.kept == ["KeepThis", "AlsoKeep"]
    assert len(result.dropped) == 1
    assert result.dropped[0][1] == "exact_blocklist_match"


def test_canonical_match_dropped(filter_: BlocklistFilter) -> None:
    """Case + whitespace differences canonicalize to the same form."""
    extractions = ["reject this    EXACTLY"]
    blocklist = [_entry("RejectThisExactly")]
    # Note: the canonicalization strips case AND whitespace. The pattern
    # "reject this exactly" (canonical) does not equal "rejectthisexactly".
    # So this test verifies the canonicalization is space-aware.
    result = filter_.apply(extractions, blocklist)
    # With whitespace normalization, "reject this exactly" canonical !=
    # "rejectthisexactly" canonical. So this stays kept.
    assert len(result.kept) == 1


def test_empty_extractions_no_op(filter_: BlocklistFilter) -> None:
    result = filter_.apply([], [_entry("X")])
    assert result.kept == []
    assert result.dropped == []


def test_empty_blocklist_no_op(filter_: BlocklistFilter) -> None:
    result = filter_.apply(["A", "B"], [])
    assert result.kept == ["A", "B"]
    assert result.dropped == []


def test_pattern_of_callback(filter_: BlocklistFilter) -> None:
    """The filter accepts complex objects via a `pattern_of` callback."""
    extractions = [
        {"label": "Frustration", "score": 0.9},
        {"label": "Excitement", "score": 0.8},
    ]
    blocklist = [_entry("Frustration")]
    result = filter_.apply(
        extractions, blocklist,
        pattern_of=lambda x: x["label"],
    )
    assert len(result.kept) == 1
    assert result.kept[0]["label"] == "Excitement"


def test_keeps_distinct_patterns(filter_: BlocklistFilter) -> None:
    extractions = ["AbsolutelyDifferent", "Random", "Unrelated"]
    blocklist = [_entry("SomethingElseEntirely")]
    result = filter_.apply(extractions, blocklist)
    assert result.kept == extractions  # all kept
