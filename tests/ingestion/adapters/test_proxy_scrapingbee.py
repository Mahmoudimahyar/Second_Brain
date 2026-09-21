"""V1.6a Phase 2 — ScrapingBeeFallback unit tests.

Per ADR-019: ScrapingBee is **opt-in per domain**. Activates only when:
  - crawl4ai returns 403/429/503 ≥ 3 times in a row, OR
  - DataDome / PerimeterX / Cloudflare-challenge markers detected.

The proxy receives URL + UA + (optional) referer only — never PII
(NFR-1.6a-8). The fallback HTML response is re-extracted locally via
the same Trafilatura/L2HtmlAdapter pipeline so the two paths produce
equivalent normalized records.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock


# ---------------------------------------------------------------------------
# Failing-first
# ---------------------------------------------------------------------------


def test_fallback_invoked_after_three_403s(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    """3 consecutive 403 -> 4th attempt routes through ScrapingBee.

    The fallback hands back the same HTML body the local fetch couldn't
    reach; the resulting CrawledRecord carries via_proxy=True.
    """

    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    os.environ["SCRAPINGBEE_API_KEY"] = "test-key-not-real"

    from src.ingestion.adapters.crawl4ai_web import Crawl4AIAdapter
    from src.ingestion.adapters.proxy_scrapingbee import (
        FallbackPolicy,
        ScrapingBeeFallback,
    )

    target = "https://protected.invalid/page"
    fixture_html = (
        b"<!DOCTYPE html><html><head><title>Behind the wall</title>"
        b"</head><body><h1>OK</h1><p>Made it through.</p></body></html>"
    )

    # robots OK
    httpx_mock.add_response(
        url="https://protected.invalid/robots.txt", status_code=404,
    )
    # Three failures.
    for _ in range(3):
        httpx_mock.add_response(url=target, status_code=403)
    # ScrapingBee returns the body. URL contains api_key + url params.
    httpx_mock.add_response(
        url=__import__("re").compile(
            r"^https://app\.scrapingbee\.com/api/v1/\?.*url=https%3A%2F%2Fprotected\.invalid%2Fpage",
        ),
        status_code=200,
        headers={"Content-Type": "text/html"},
        content=fixture_html,
    )

    fallback = ScrapingBeeFallback(api_key=os.environ["SCRAPINGBEE_API_KEY"])
    adapter = Crawl4AIAdapter(
        source_tier="L2",
        cache_dir=tmp_path / "wc",
        fallback=fallback,
        fallback_policy=FallbackPolicy(
            enabled=True,
            consecutive_failures_to_trigger=3,
        ),
    )
    record = asyncio.run(adapter.fetch_url(target))
    assert record.via_proxy is True
    assert record.title == "Behind the wall"
    assert "made it through" in record.body_md.lower()


# ---------------------------------------------------------------------------
# Default-off (opt-in only)
# ---------------------------------------------------------------------------


def test_fallback_disabled_by_default(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    """Without explicit opt-in the proxy is never consulted, even on persistent 403."""

    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.adapters.crawl4ai_web import Crawl4AIAdapter

    httpx_mock.add_response(
        url="https://blocked.invalid/robots.txt", status_code=404,
    )
    # The adapter retries 3x by default; register one response per attempt.
    for _ in range(3):
        httpx_mock.add_response(
            url="https://blocked.invalid/page", status_code=403,
        )

    adapter = Crawl4AIAdapter(
        source_tier="L2", cache_dir=tmp_path / "wc",
    )
    # No fallback configured -> retries exhaust -> raise on the last 403.
    with pytest.raises(Exception):  # noqa: B017,PT011 — any HTTP error is fine here
        asyncio.run(adapter.fetch_url("https://blocked.invalid/page"))


# ---------------------------------------------------------------------------
# DataDome / PerimeterX / CF challenge detection
# ---------------------------------------------------------------------------


def test_fallback_invoked_on_datadome_detection(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    """A 200 response with `Server: DataDome` triggers the fallback on the
    NEXT fetch attempt — the detection short-circuits the failure counter."""

    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    os.environ["SCRAPINGBEE_API_KEY"] = "test-key"

    from src.ingestion.adapters.crawl4ai_web import Crawl4AIAdapter
    from src.ingestion.adapters.proxy_scrapingbee import (
        FallbackPolicy,
        ScrapingBeeFallback,
        detect_anti_bot,
    )

    headers = {"Server": "DataDome", "Content-Type": "text/html"}
    body = b"<html><title>blocked</title><body>nope</body></html>"
    assert detect_anti_bot(headers=headers, body=body) is True

    httpx_mock.add_response(
        url="https://gated.invalid/robots.txt", status_code=404,
    )
    httpx_mock.add_response(
        url="https://gated.invalid/page",
        status_code=200,
        headers=headers,
        content=body,
    )
    httpx_mock.add_response(
        url=__import__("re").compile(
            r"^https://app\.scrapingbee\.com/api/v1/\?.*url=https%3A%2F%2Fgated\.invalid%2Fpage",
        ),
        status_code=200,
        headers={"Content-Type": "text/html"},
        content=b"<html><title>Bypassed</title><body>Real content</body></html>",
    )

    adapter = Crawl4AIAdapter(
        source_tier="L2",
        cache_dir=tmp_path / "wc",
        fallback=ScrapingBeeFallback(api_key="test-key"),
        fallback_policy=FallbackPolicy(enabled=True),
    )
    record = asyncio.run(adapter.fetch_url("https://gated.invalid/page"))
    assert record.via_proxy is True
    assert record.title == "Bypassed"


def test_detect_anti_bot_perimeterx() -> None:
    from src.ingestion.adapters.proxy_scrapingbee import detect_anti_bot

    assert detect_anti_bot(
        headers={"Set-Cookie": "_pxhd=abc"},
        body=b"<html>blocked</html>",
    ) is True


def test_detect_anti_bot_cloudflare() -> None:
    from src.ingestion.adapters.proxy_scrapingbee import detect_anti_bot

    assert detect_anti_bot(
        headers={"Cf-Mitigated": "challenge"},
        body=b"",
    ) is True


def test_detect_anti_bot_clean_html_false() -> None:
    from src.ingestion.adapters.proxy_scrapingbee import detect_anti_bot

    assert detect_anti_bot(
        headers={"Content-Type": "text/html"},
        body=b"<html><body>normal page</body></html>",
    ) is False


# ---------------------------------------------------------------------------
# PII non-leakage (NFR-1.6a-8)
# ---------------------------------------------------------------------------


def test_no_pii_leakage_in_request(httpx_mock: HTTPXMock) -> None:
    """The ScrapingBee request URL contains only api_key + url + render_js +
    premium_proxy + country_code. No PII, no chat history, no SecBrain-internal
    identifiers."""

    from src.ingestion.adapters.proxy_scrapingbee import ScrapingBeeFallback

    httpx_mock.add_response(
        url=__import__("re").compile(r"^https://app\.scrapingbee\.com/api/v1/"),
        status_code=200,
        headers={"Content-Type": "text/html"},
        content=b"<html><title>ok</title></html>",
    )

    fb = ScrapingBeeFallback(api_key="test-key")
    asyncio.run(fb.fetch(
        "https://target.invalid/page",
        user_agent="SecBrain/1.6 (+test@example.invalid)",
    ))

    # Inspect what was actually sent to ScrapingBee.
    sent = httpx_mock.get_requests(
        url=__import__("re").compile(r"^https://app\.scrapingbee\.com/api/v1/"),
    )
    assert sent, "ScrapingBee was never called"
    url = str(sent[0].url)
    allowed_keys = {"api_key", "url", "render_js", "premium_proxy", "country_code"}
    from urllib.parse import parse_qs, urlparse
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert set(qs.keys()).issubset(allowed_keys), (
        f"unexpected params in ScrapingBee URL: "
        f"{set(qs.keys()) - allowed_keys}"
    )
    # No SecBrain-internal markers in URL
    assert "secbrain" not in url.lower()
    # UA goes in the `Spb-Header-User-Agent` request header, NOT the query.
    assert "user_agent" not in qs
    # Confirm UA actually rode in the header path (so we know it wasn't dropped).
    assert sent[0].headers.get("Spb-Header-User-Agent") == (
        "SecBrain/1.6 (+test@example.invalid)"
    )


# ---------------------------------------------------------------------------
# Health-check
# ---------------------------------------------------------------------------


def test_health_check_succeeds_with_valid_key(httpx_mock: HTTPXMock) -> None:
    from src.ingestion.adapters.proxy_scrapingbee import ScrapingBeeFallback

    httpx_mock.add_response(
        url=__import__("re").compile(r"^https://app\.scrapingbee\.com/api/v1/"),
        status_code=200,
        headers={"Content-Type": "text/html"},
        content=b"<html>ok</html>",
    )

    fb = ScrapingBeeFallback(api_key="valid-key")
    health = asyncio.run(fb.health_check())
    assert health.ok is True
    assert health.status_code == 200


def test_health_check_fails_with_invalid_key(httpx_mock: HTTPXMock) -> None:
    from src.ingestion.adapters.proxy_scrapingbee import ScrapingBeeFallback

    httpx_mock.add_response(
        url=__import__("re").compile(r"^https://app\.scrapingbee\.com/api/v1/"),
        status_code=401,
    )

    fb = ScrapingBeeFallback(api_key="bad-key")
    health = asyncio.run(fb.health_check())
    assert health.ok is False
    assert health.status_code == 401
