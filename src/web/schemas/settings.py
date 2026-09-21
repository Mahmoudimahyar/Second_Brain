"""Response/request schemas for ``/api/v1/settings/*``."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FeedbackLoopPolicy(BaseModel):
    """``/api/v1/settings/feedback-loop`` shape."""

    model_config = ConfigDict(extra="forbid")

    positive_k: int = 4
    blocklist_cap: int = 50
    half_life_days: float = 90.0
    w_relevance: float = 0.4
    w_recency: float = 0.2
    w_diversity: float = 0.3
    w_freq: float = 0.1
    active_examples: list[dict[str, Any]] = Field(default_factory=list)
    active_blocklist: list[dict[str, Any]] = Field(default_factory=list)


class CorpusSummary(BaseModel):
    """``/api/v1/settings/corpora`` row."""

    model_config = ConfigDict(extra="forbid")

    corpus_id: str
    label: str | None = None
    node_count: int = 0
    edge_count: int = 0
    last_ingest_at: str | None = None


class CorporaListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corpora: list[CorpusSummary] = Field(default_factory=list)


class WebSearchSettings(BaseModel):
    """``/api/v1/settings/web-search`` shape."""

    model_config = ConfigDict(extra="forbid")

    cap_usd_per_corpus: float = 5.0
    providers: list[dict[str, Any]] = Field(default_factory=list)
    tavily_key_present: bool = False


__all__ = [
    "CorporaListResponse",
    "CorpusSummary",
    "FeedbackLoopPolicy",
    "WebSearchSettings",
]
