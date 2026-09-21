"""Schemas for `/api/v1/ask` — NL question over the knowledge graph."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class AskResponse(BaseModel):
    question: str
    intent: str | None = None
    answer: str | None = Field(
        default=None,
        description="LLM-grounded answer; null when no LLM key is available "
                    "(facts-only degradation).",
    )
    facts: dict[str, Any] = Field(
        default_factory=dict,
        description="Deterministic graph retrieval the answer is grounded in.",
    )
