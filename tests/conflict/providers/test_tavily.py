"""Tests for V1.5c Phase 1 — `TavilyProvider` (ADR-016 v2)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from src.conflict.providers.tavily import TavilyProvider
from src.shared.errors import ErrorCode, StructuredError


class _MockTavilyClient:
    def __init__(
        self,
        qna_response: dict[str, Any] | None = None,
        search_response: dict[str, Any] | None = None,
        extract_response: dict[str, Any] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._qna = qna_response or {}
        self._search = search_response or {}
        self._extract = extract_response or {}
        self._raises = raises
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def qna_search(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("qna_search", kwargs))
        if self._raises is not None:
            raise self._raises
        return self._qna

    def search(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("search", kwargs))
        if self._raises is not None:
            raise self._raises
        return self._search

    def extract(self, urls: list[str], **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("extract", {"urls": urls, **kwargs}))
        if self._raises is not None:
            raise self._raises
        return self._extract


def _provider(client: _MockTavilyClient, **overrides: Any) -> TavilyProvider:
    return TavilyProvider(
        api_key="tvly-test-key",
        client_factory=lambda _key: client,
        max_retries=1,  # tighter retries for tests
        **overrides,
    )


def test_qna_search_returns_answer_and_urls() -> None:
    client = _MockTavilyClient(
        qna_response={
            "answer": "NYU dental tuition for 2024-25 was $87,000.",
            "results": [
                {"url": "https://dental.nyu.edu/tuition"},
                {"url": "https://example.org/fact-check"},
            ],
        },
    )
    provider = _provider(client)
    res = provider.qna_search("What was NYU dental tuition in 2024-25?")
    assert "87,000" in res.answer
    assert "https://dental.nyu.edu/tuition" in res.urls
    assert res.provider == "tavily"
    # >= 0, not > 0: the client is an instant mock, and on Windows + Python 3.12
    # time.monotonic() ticks every ~15 ms, so the measured latency is exactly 0.0.
    assert res.latency_ms >= 0


def test_search_returns_synthesized_answer() -> None:
    client = _MockTavilyClient(
        search_response={
            "answer": "Pre-dental applicants need a DAT score around 21+.",
            "results": [{"url": "https://adea.org/dat"}],
        },
    )
    res = _provider(client).search("DAT score for dental school")
    assert "21" in res.answer
    assert "adea.org" in res.urls[0]


def test_extract_returns_clean_pages() -> None:
    client = _MockTavilyClient(
        extract_response={
            "results": [
                {
                    "url": "https://x.org",
                    "title": "X",
                    "content": "Body text",
                    "raw_content": "Raw body",
                },
            ],
            "failed_results": [],
        },
    )
    pages = _provider(client).extract(["https://x.org"])
    assert len(pages) == 1
    assert pages[0].url == "https://x.org"
    assert pages[0].text == "Raw body"
    assert pages[0].success


def test_extract_reports_failed_urls() -> None:
    client = _MockTavilyClient(
        extract_response={
            "results": [],
            "failed_results": [
                {"url": "https://broken.example", "error": "404 Not Found"},
            ],
        },
    )
    pages = _provider(client).extract(["https://broken.example"])
    assert pages[0].success is False
    assert pages[0].error == "404 Not Found"


def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with pytest.raises(StructuredError) as excinfo:
        TavilyProvider()
    assert excinfo.value.error_code == ErrorCode.CRED_NOT_FOUND


def test_retry_backoff_then_succeed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _s: None)

    call_counter = {"n": 0}

    class _FlakyClient:
        def qna_search(self, **_: Any) -> dict[str, Any]:
            call_counter["n"] += 1
            if call_counter["n"] < 2:
                raise httpx.RequestError("flaky 503")
            return {"answer": "ok", "results": []}

    provider = TavilyProvider(
        api_key="x",
        client_factory=lambda _k: _FlakyClient(),
        max_retries=3,
    )
    res = provider.qna_search("q")
    assert res.answer == "ok"
    assert call_counter["n"] == 2


def test_fails_after_max_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _s: None)
    client = _MockTavilyClient(raises=httpx.RequestError("persistent 503"))
    provider = TavilyProvider(
        api_key="x",
        client_factory=lambda _k: client,
        max_retries=2,
    )
    with pytest.raises(StructuredError) as excinfo:
        provider.qna_search("q")
    assert excinfo.value.error_code == ErrorCode.CONNECTION_FAILED


def test_cost_callback_called() -> None:
    costs: list[tuple[str, float]] = []
    client = _MockTavilyClient(qna_response={"answer": "x", "results": []})
    provider = TavilyProvider(
        api_key="x",
        client_factory=lambda _k: client,
        max_retries=1,
        cost_callback=lambda op, c: costs.append((op, c)),
    )
    provider.qna_search("q")
    assert costs == [("qna_search", 0.008)]


def test_extract_empty_returns_empty() -> None:
    client = _MockTavilyClient()
    pages = _provider(client).extract([])
    assert pages == []
    # No call should have been made
    assert not client.calls
