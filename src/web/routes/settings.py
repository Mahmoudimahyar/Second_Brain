"""V1.5b — `/api/v1/settings` routes (feedback-loop policy + corpora)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Query

from src.embeddings.hash_embedder import HashEmbeddingService
from src.extraction.feedback_context import (
    ActiveLearningWeights,
    FeedbackContextLoader,
)
from src.extraction.feedback_log import FeedbackLog
from src.web.paths import sqlite_path

router = APIRouter()


def _feedback_log() -> FeedbackLog:
    return FeedbackLog(sqlite_path=sqlite_path())


@router.get("/feedback-loop")
def view_feedback_loop(
    corpus_id: str = Query(...),
    prompt_template_id: str = Query(...),
) -> dict[str, Any]:
    """Return the active ContextBlock for a (corpus, template) pair.

    Used by `/settings/feedback-loop` UI to render the live context block +
    blocklist that Pass 4 will see on its next invocation.
    """

    loader = FeedbackContextLoader(
        feedback_log=_feedback_log(),
        embedding_service=HashEmbeddingService(),
    )
    block = loader.build(
        corpus_id=corpus_id, prompt_template_id=prompt_template_id,
    )
    return {
        "corpus_id": block.corpus_id,
        "prompt_template_id": block.prompt_template_id,
        "examples": [e.model_dump() for e in block.examples],
        "blocklist": [b.model_dump() for b in block.blocklist],
        "context_hash": block.context_hash,
        "feedback_log_count": block.feedback_log_count,
    }


@router.post("/feedback-loop/decisions")
def append_decision(
    payload: Annotated[dict[str, Any], Body(...)],
) -> dict[str, Any]:
    """Append a manual feedback decision (operator override)."""

    log = _feedback_log()
    entry = log.append(
        corpus_id=str(payload["corpus_id"]),
        item_type=str(payload.get("item_type", "settings_override")),
        pattern=str(payload["pattern"]),
        verdict=payload["verdict"],
        decided_by=str(payload.get("decided_by", "settings_override")),
        prompt_template_id=payload.get("prompt_template_id"),
        refinement=payload.get("refinement"),
    )
    return {
        "feedback_id": entry.feedback_id,
        "verdict": entry.verdict,
    }


@router.get("/feedback-loop/policy")
def get_policy() -> dict[str, Any]:
    """Return the active scoring weights + caps."""

    w = ActiveLearningWeights()
    return {
        "weights": {
            "relevance": w.relevance,
            "recency": w.recency,
            "diversity": w.diversity,
            "frequency": w.frequency,
            "half_life_days": w.half_life_days,
            "min_diversity_distance": w.min_diversity_distance,
        },
        "caps": {
            "positive_examples_k": FeedbackContextLoader.POSITIVE_K,
            "blocklist_max": FeedbackContextLoader.BLOCKLIST_CAP,
        },
    }


@router.get("/corpora")
def list_corpora() -> dict[str, Any]:
    """Return distinct corpora known to the feedback log.

    V1.5b minimal — V1.6 extends with corpus-level metadata.
    """

    import sqlite3  # noqa: PLC0415

    with sqlite3.connect(sqlite_path()) as conn:
        rows = conn.execute(
            "SELECT corpus_id, COUNT(*) AS n FROM feedback_log "
            "GROUP BY corpus_id ORDER BY n DESC",
        ).fetchall()
    return {
        "corpora": [
            {"corpus_id": str(c), "decision_count": int(n)}
            for c, n in rows
        ],
    }
