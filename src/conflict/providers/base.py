"""V1.5c — `SearchProvider` Protocol (ADR-016 v2).

Three surface methods:
- `qna_search(question)` — synthesized answer + URLs (Tavily QNA).
- `search(query)` — ranked URLs + optional synthesized answer.
- `extract(urls)` — clean page text per URL.

V1.5c ships Tavily only. V1.6 candidates: Brave, Firecrawl, Exa. The
Protocol keeps providers swappable.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class SearchAnswer(BaseModel):
    """One synthesized answer to a question, with supporting URLs."""

    model_config = ConfigDict(extra="forbid")

    answer: str
    urls: list[str] = Field(default_factory=list)
    raw_response: dict[str, Any] = Field(default_factory=dict)
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    provider: str = "unknown"


class SearchResult(BaseModel):
    """One ranked search hit."""

    model_config = ConfigDict(extra="forbid")

    url: str
    title: str = ""
    snippet: str = ""
    raw_score: float = 0.0


class ExtractedPage(BaseModel):
    """Clean-text extraction of one URL."""

    model_config = ConfigDict(extra="forbid")

    url: str
    title: str = ""
    text: str = ""
    raw_html: str = ""
    success: bool = True
    error: str | None = None


@runtime_checkable
class SearchProvider(Protocol):
    name: str

    def qna_search(
        self, question: str, *, max_results: int = 5,
    ) -> SearchAnswer: ...

    def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        search_depth: str = "advanced",
    ) -> SearchAnswer: ...

    def extract(
        self, urls: list[str], *, extract_depth: str = "advanced",
    ) -> list[ExtractedPage]: ...


__all__ = [
    "ExtractedPage",
    "SearchAnswer",
    "SearchProvider",
    "SearchResult",
]
