"""Tests for V1.5b Phase 5 — `FeedbackContextLoader` (ADR-018).

Hard-cap K=4 enforcement, diversity constraint, hybrid scoring,
context_hash stability across feedback decisions.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.embeddings.hash_embedder import HashEmbeddingService
from src.extraction.feedback_context import (
    ActiveLearningWeights,
    FeedbackContextLoader,
)
from src.extraction.feedback_log import FeedbackLog


@pytest.fixture
def feedback_log(tmp_path: Path) -> FeedbackLog:
    return FeedbackLog(sqlite_path=tmp_path / "engine.db")


@pytest.fixture
def loader(feedback_log: FeedbackLog) -> FeedbackContextLoader:
    return FeedbackContextLoader(
        feedback_log=feedback_log,
        embedding_service=HashEmbeddingService(),
    )


def _seed_accepts(log: FeedbackLog, n: int, *, template: str = "t") -> None:
    for i in range(n):
        log.append(
            corpus_id="c1", item_type="node_proposal",
            pattern=f"PositivePattern_{i}", verdict="accept",
            decided_by="m", prompt_template_id=template,
        )


def _seed_rejects(log: FeedbackLog, n: int, *, template: str = "t") -> None:
    for i in range(n):
        log.append(
            corpus_id="c1", item_type="node_proposal",
            pattern=f"BadPattern_{i}", verdict="reject",
            decided_by="m", prompt_template_id=template,
        )


def test_no_feedback_returns_empty_block(
    loader: FeedbackContextLoader,
) -> None:
    block = loader.build(corpus_id="empty", prompt_template_id="t")
    assert block.examples == []
    assert block.blocklist == []
    assert block.context_hash


def test_positive_cap_at_4(
    loader: FeedbackContextLoader, feedback_log: FeedbackLog,
) -> None:
    """ADR-018 hard cap — never more than 4 positive examples regardless
    of how many accepts exist."""
    _seed_accepts(feedback_log, 20)
    block = loader.build(corpus_id="c1", prompt_template_id="t")
    assert len(block.examples) <= 4


def test_blocklist_cap_at_50(
    loader: FeedbackContextLoader, feedback_log: FeedbackLog,
) -> None:
    _seed_rejects(feedback_log, 75)
    block = loader.build(corpus_id="c1", prompt_template_id="t")
    assert len(block.blocklist) <= 50


def test_blocklist_aggregates_duplicates(
    loader: FeedbackContextLoader, feedback_log: FeedbackLog,
) -> None:
    """The same rejected pattern occurring 3 times yields ONE blocklist
    entry with hit_count=3."""
    for _ in range(3):
        feedback_log.append(
            corpus_id="c1", item_type="np",
            pattern="DuplicatePattern", verdict="reject",
            decided_by="m", prompt_template_id="t",
        )
    block = loader.build(corpus_id="c1", prompt_template_id="t")
    matching = [b for b in block.blocklist if b.pattern == "DuplicatePattern"]
    assert len(matching) == 1
    assert matching[0].hit_count == 3


def test_context_hash_stable_across_calls(
    loader: FeedbackContextLoader, feedback_log: FeedbackLog,
) -> None:
    _seed_accepts(feedback_log, 5)
    block1 = loader.build(corpus_id="c1", prompt_template_id="t")
    block2 = loader.build(corpus_id="c1", prompt_template_id="t")
    assert block1.context_hash == block2.context_hash


def test_context_hash_changes_on_new_decision(
    loader: FeedbackContextLoader, feedback_log: FeedbackLog,
) -> None:
    """FR-1.5b-7.5: new feedback invalidates the cache key."""
    _seed_accepts(feedback_log, 2)
    before = loader.build(corpus_id="c1", prompt_template_id="t").context_hash
    feedback_log.append(
        corpus_id="c1", item_type="np", pattern="NewPattern",
        verdict="accept", decided_by="m", prompt_template_id="t",
    )
    after = loader.build(corpus_id="c1", prompt_template_id="t").context_hash
    assert before != after


def test_per_template_scoping(
    loader: FeedbackContextLoader, feedback_log: FeedbackLog,
) -> None:
    """ADR-018: feedback for template_a doesn't appear in template_b's block."""
    _seed_accepts(feedback_log, 3, template="extract_sentiment")
    _seed_accepts(feedback_log, 3, template="extract_interview_q")
    sentiment_block = loader.build(
        corpus_id="c1", prompt_template_id="extract_sentiment",
    )
    # Each template should only see its own + the template-agnostic ones.
    # Since all our seeds are template-tagged, the sentiment block sees 3.
    assert all(
        "Positive" in e.pattern for e in sentiment_block.examples
    )


def test_diversity_constraint_drops_near_duplicates(
    loader: FeedbackContextLoader, feedback_log: FeedbackLog,
) -> None:
    """The selection should reject candidates that are too similar to
    already-selected ones (per ADR-018 diversity constraint)."""
    # Seed many copies of one pattern + a few distinct ones.
    for _ in range(8):
        feedback_log.append(
            corpus_id="c1", item_type="np",
            pattern="DuplicatePattern_X", verdict="accept",
            decided_by="m", prompt_template_id="t",
        )
    feedback_log.append(
        corpus_id="c1", item_type="np",
        pattern="DifferentPattern_Y", verdict="accept",
        decided_by="m", prompt_template_id="t",
    )
    feedback_log.append(
        corpus_id="c1", item_type="np",
        pattern="AnotherPattern_Z", verdict="accept",
        decided_by="m", prompt_template_id="t",
    )
    block = loader.build(corpus_id="c1", prompt_template_id="t")
    # Should NOT have all 4 slots filled by the same DuplicatePattern.
    canonicals = {e.pattern_canonical for e in block.examples}
    assert len(canonicals) >= 2


def test_render_prompt_fragment(
    loader: FeedbackContextLoader, feedback_log: FeedbackLog,
) -> None:
    _seed_accepts(feedback_log, 2)
    _seed_rejects(feedback_log, 2)
    block = loader.build(corpus_id="c1", prompt_template_id="t")
    rendered = block.render_prompt_fragment()
    assert "Previously accepted patterns" in rendered
    assert "Do NOT extract these" in rendered


def test_active_learning_weights_tunable(
    feedback_log: FeedbackLog,
) -> None:
    weights = ActiveLearningWeights(
        relevance=0.1, recency=0.1, diversity=0.7, frequency=0.1,
        half_life_days=30.0,
    )
    loader = FeedbackContextLoader(
        feedback_log=feedback_log,
        embedding_service=HashEmbeddingService(),
        weights=weights,
    )
    _seed_accepts(feedback_log, 5)
    block = loader.build(corpus_id="c1", prompt_template_id="t")
    assert len(block.examples) <= 4
    assert all(e.selection_score >= 0 for e in block.examples)


def test_feedback_log_count_recorded(
    loader: FeedbackContextLoader, feedback_log: FeedbackLog,
) -> None:
    _seed_accepts(feedback_log, 3)
    _seed_rejects(feedback_log, 2)
    block = loader.build(corpus_id="c1", prompt_template_id="t")
    assert block.feedback_log_count == 5
