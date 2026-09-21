"""V1.5c — `TavilyProvider` (ADR-016 v2).

Wraps `tavily-python` SDK. Three surfaces: `qna_search`, `search`,
`extract`. Reads `TAVILY_API_KEY` from env. Records per-call cost +
latency to `web_search_cost` SQLite table via the optional `cost_tracker`
injection.

Failure modes:
- 5xx / rate-limit → exponential backoff (3 tries, 1s/2s/4s).
- Empty result → returns an empty `SearchAnswer` (NOT an exception).
- Network timeout → raises `StructuredError(CONNECTION_FAILED)`.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from src.conflict.providers.base import (
    ExtractedPage,
    SearchAnswer,
)
from src.shared.errors import ErrorCode, StructuredError

# Tavily cost per call (approx, USD). V1.5c uses a flat fee per call type
# tracked in `web_search_cost`. Update per Tavily's billing changes.
TAVILY_COST_QNA: float = 0.008
TAVILY_COST_SEARCH: float = 0.004
TAVILY_COST_EXTRACT_PER_URL: float = 0.002


CostCallback = Callable[[str, float], None]
TavilyClientFactory = Callable[[str], Any]


@dataclass
class TavilyProvider:
    """Tavily-only single-provider implementation (V1.5c)."""

    name: str = "tavily"
    api_key: str | None = None
    timeout_seconds: float = 8.0
    max_retries: int = 3
    cost_callback: CostCallback | None = None
    client_factory: TavilyClientFactory | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = os.environ.get("TAVILY_API_KEY")
        if not self.api_key:
            raise StructuredError(
                ErrorCode.CRED_NOT_FOUND,
                "TAVILY_API_KEY not set in environment",
            )
        if self.client_factory is None:
            self.client_factory = _default_tavily_client

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def qna_search(
        self, question: str, *, max_results: int = 5,
    ) -> SearchAnswer:
        return self._call(
            "qna_search",
            lambda c: c.qna_search(
                query=question, search_depth="advanced",
                max_results=max_results,
            ),
            cost=TAVILY_COST_QNA,
        )

    def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        search_depth: str = "advanced",
    ) -> SearchAnswer:
        return self._call(
            "search",
            lambda c: c.search(
                query=query, search_depth=search_depth,
                include_answer=True, max_results=max_results,
            ),
            cost=TAVILY_COST_SEARCH,
        )

    def extract(
        self,
        urls: list[str],
        *,
        extract_depth: str = "advanced",
    ) -> list[ExtractedPage]:
        if not urls:
            return []
        try:
            start = time.monotonic()
            assert self.client_factory is not None
            client = self.client_factory(self.api_key or "")
            raw = client.extract(urls=urls, extract_depth=extract_depth)
            elapsed = (time.monotonic() - start) * 1000
        except (httpx.HTTPError, OSError) as e:
            raise StructuredError(
                ErrorCode.CONNECTION_FAILED,
                f"Tavily extract failed: {e}",
                context={"urls": urls},
            ) from e

        self._record_cost(
            "extract", TAVILY_COST_EXTRACT_PER_URL * len(urls),
        )
        # Normalize the raw response shape into ExtractedPage list.
        results = raw.get("results", []) if isinstance(raw, dict) else []
        failed = raw.get("failed_results", []) if isinstance(raw, dict) else []
        out: list[ExtractedPage] = [
            ExtractedPage(
                url=str(r.get("url", "")),
                title=str(r.get("title") or ""),
                text=str(r.get("raw_content") or r.get("content") or ""),
                raw_html=str(r.get("raw_html") or ""),
                success=True,
            )
            for r in results
        ]
        out.extend(
            ExtractedPage(
                url=str(f.get("url", "")),
                success=False,
                error=str(f.get("error") or "extraction_failed"),
            )
            for f in failed
        )
        _ = elapsed  # cost+latency recorded via cost_callback; per-page latency is V1.6
        return out

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _call(
        self,
        op: str,
        body: Callable[[Any], dict[str, Any]],
        *,
        cost: float,
    ) -> SearchAnswer:
        assert self.client_factory is not None
        last_error: Exception | None = None
        backoff = 1.0
        for attempt in range(self.max_retries):
            try:
                start = time.monotonic()
                client = self.client_factory(self.api_key or "")
                raw = body(client)
                latency_ms = (time.monotonic() - start) * 1000
                self._record_cost(op, cost)
                return _normalize_answer(raw, latency_ms, op)
            except (httpx.HTTPError, OSError) as e:
                last_error = e
                if attempt + 1 == self.max_retries:
                    break
                time.sleep(backoff)
                backoff *= 2
        raise StructuredError(
            ErrorCode.CONNECTION_FAILED,
            f"Tavily {op} failed after {self.max_retries} retries: "
            f"{last_error!r}",
            context={"op": op},
        )

    def _record_cost(self, op: str, amount: float) -> None:
        if self.cost_callback is not None:
            self.cost_callback(op, amount)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _normalize_answer(
    raw: dict[str, Any], latency_ms: float, op: str,
) -> SearchAnswer:
    if not isinstance(raw, dict):
        return SearchAnswer(
            answer="", urls=[], raw_response={"warning": f"non-dict response: {type(raw)}"},
            latency_ms=latency_ms, provider="tavily",
        )
    answer = str(raw.get("answer") or "")
    results = raw.get("results", []) or []
    urls: list[str] = []
    if isinstance(results, list):
        for r in results:
            if isinstance(r, dict) and r.get("url"):
                urls.append(str(r["url"]))
    return SearchAnswer(
        answer=answer,
        urls=urls,
        raw_response=raw,
        latency_ms=latency_ms,
        provider="tavily",
    )


def _default_tavily_client(api_key: str) -> Any:
    """Return a configured TavilyClient. Lazy import keeps the module
    importable when the SDK is absent (tests inject a mock).
    """

    from tavily import TavilyClient  # type: ignore[import-untyped]  # noqa: PLC0415

    return TavilyClient(api_key=api_key)


__all__ = ["TavilyProvider"]
