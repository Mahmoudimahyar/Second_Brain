"""V1.6a Phase 1 — Crawl4AIAdapter unit tests.

TDD per AGENTS.md. Each test below precedes the production code commit by
at least one cycle. The adapter takes an injectable async fetch callable so
HTTP can be mocked with pytest-httpx; crawl4ai's AsyncWebCrawler is the
production fetcher and the same `CrawledRecord` shape comes out either way.

Test domains in `tests/fixtures/web/` are served via pytest-httpx routing
keyed on the URL → fixture path map. No real network.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock


def _stub_robots(httpx_mock: HTTPXMock, fqdn: str, *, allow: bool = True, body: bytes | None = None) -> None:
    """Convenience: register robots.txt for `fqdn`.

    The adapter fetches /robots.txt before every URL; tests pre-register
    a 404 (default-allow) or a real body when they want to assert
    Disallow / Crawl-delay behavior.
    """
    if body is not None:
        httpx_mock.add_response(
            url=f"https://{fqdn}/robots.txt",
            status_code=200,
            content=body,
        )
    elif allow:
        httpx_mock.add_response(
            url=f"https://{fqdn}/robots.txt",
            status_code=404,
        )
    else:
        httpx_mock.add_response(
            url=f"https://{fqdn}/robots.txt",
            status_code=200,
            content=b"User-agent: *\nDisallow: /\n",
        )


# ---------------------------------------------------------------------------
# Sample HTML for the failing-first round-trip test
# ---------------------------------------------------------------------------

_FIXTURE_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>ADEA Cost of Attendance · 2024–25</title>
  <link rel="canonical" href="https://www.adea.org/coa/2024-25/" />
</head>
<body>
  <h1>Cost of Attendance Survey 2024–25</h1>
  <p>The ADEA Survey of Dental School Seniors reports tuition + fees
  + living expenses across U.S. dental schools.</p>
  <p>Median first-year resident tuition was $48,200 in 2024–25.</p>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Phase 1.1 — failing-first
# ---------------------------------------------------------------------------


def test_html_page_round_trip_extracts_title_and_body(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    """Fetch one URL → assert title + body + content_hash + mime are right.

    Failing-first per V1.6a Phase 1 (plan.md). Pre-condition: a valid
    CRAWL4AI_USER_AGENT env var. The adapter:

    1. Requests the URL via injected httpx.AsyncClient (or default).
    2. Honors no-robots-txt-needed for a one-off fetch_url() call.
    3. Returns a CrawledRecord with normalized fields.
    """

    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.adapters.crawl4ai_web import Crawl4AIAdapter

    _stub_robots(httpx_mock, "www.adea.org")
    httpx_mock.add_response(
        url="https://www.adea.org/coa/2024-25/",
        status_code=200,
        headers={
            "Content-Type": "text/html; charset=utf-8",
            "ETag": '"abc123"',
            "Last-Modified": "Wed, 01 May 2024 12:00:00 GMT",
        },
        content=_FIXTURE_HTML.encode("utf-8"),
    )

    adapter = Crawl4AIAdapter(
        source_tier="L2",
        cache_dir=tmp_path / "web_cache",
    )
    record = asyncio.run(
        adapter.fetch_url("https://www.adea.org/coa/2024-25/"),
    )

    assert record.url == "https://www.adea.org/coa/2024-25/"
    assert record.mime == "text/html"
    assert record.title == "ADEA Cost of Attendance · 2024–25"
    assert "median first-year resident tuition was $48,200" in record.body_md.lower()
    assert record.content_hash  # sha256 hex digest
    assert len(record.content_hash) == 64
    assert record.etag == '"abc123"'
    assert record.bytes_ > 0
    assert record.via_proxy is False
    assert record.source_tier == "L2"


# ---------------------------------------------------------------------------
# Phase 1.2 — politeness contracts
# ---------------------------------------------------------------------------


def test_user_agent_env_required_or_raises(tmp_path: Path) -> None:
    """NFR-1.6a-6: the adapter refuses to start without CRAWL4AI_USER_AGENT.

    This is non-overridable; a missing UA implies anonymous fetching which
    violates the politeness contract.
    """

    os.environ.pop("CRAWL4AI_USER_AGENT", None)
    from src.ingestion.adapters.crawl4ai_web import Crawl4AIAdapter

    with pytest.raises(RuntimeError, match="CRAWL4AI_USER_AGENT"):
        Crawl4AIAdapter(source_tier="L2", cache_dir=tmp_path / "wc")


def test_user_agent_env_empty_string_raises(tmp_path: Path) -> None:
    os.environ["CRAWL4AI_USER_AGENT"] = ""
    from src.ingestion.adapters.crawl4ai_web import Crawl4AIAdapter

    with pytest.raises(RuntimeError, match="CRAWL4AI_USER_AGENT"):
        Crawl4AIAdapter(source_tier="L2", cache_dir=tmp_path / "wc")


# ---------------------------------------------------------------------------
# Phase 1.3 — robots.txt
# ---------------------------------------------------------------------------


def test_robots_absent_treats_as_all_allowed(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.adapters.crawl4ai_web import Crawl4AIAdapter

    httpx_mock.add_response(
        url="https://example.invalid/robots.txt",
        status_code=404,
    )
    adapter = Crawl4AIAdapter(
        source_tier="L2", cache_dir=tmp_path / "wc",
    )
    allowed = asyncio.run(adapter.is_allowed_by_robots(
        "https://example.invalid/page",
    ))
    assert allowed is True


def test_robots_disallow_blocks_url(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    """robots.txt `Disallow: /private/` → URLs in /private/ blocked at adapter."""
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.adapters.crawl4ai_web import Crawl4AIAdapter

    robots_body = b"User-agent: *\nDisallow: /private/\n"
    httpx_mock.add_response(
        url="https://example.invalid/robots.txt",
        status_code=200,
        content=robots_body,
    )

    adapter = Crawl4AIAdapter(
        source_tier="L2", cache_dir=tmp_path / "wc",
    )
    blocked = asyncio.run(adapter.is_allowed_by_robots(
        "https://example.invalid/private/foo.html",
    ))
    public = asyncio.run(adapter.is_allowed_by_robots(
        "https://example.invalid/public/foo.html",
    ))
    assert blocked is False
    assert public is True


def test_robots_crawl_delay_honored(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    """robots.txt `Crawl-delay: 2` → adapter reports 2s as the per-domain pace."""
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.adapters.crawl4ai_web import Crawl4AIAdapter

    httpx_mock.add_response(
        url="https://example.invalid/robots.txt",
        status_code=200,
        content=b"User-agent: *\nCrawl-delay: 2\n",
    )

    adapter = Crawl4AIAdapter(
        source_tier="L2", cache_dir=tmp_path / "wc",
    )
    delay = asyncio.run(adapter.crawl_delay("https://example.invalid/"))
    assert delay == pytest.approx(2.0)


def test_robots_crawl_delay_clamped_to_max(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    """A pathological Crawl-delay (e.g. 60) is clamped to the politeness cap."""
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.adapters.crawl4ai_web import Crawl4AIAdapter

    httpx_mock.add_response(
        url="https://example.invalid/robots.txt",
        status_code=200,
        content=b"User-agent: *\nCrawl-delay: 60\n",
    )

    adapter = Crawl4AIAdapter(
        source_tier="L2", cache_dir=tmp_path / "wc",
    )
    delay = asyncio.run(adapter.crawl_delay("https://example.invalid/"))
    # Per ADR-019: clamped to 0.5–10s range.
    assert delay == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Phase 1.4 — per-page content cache
# ---------------------------------------------------------------------------


def test_etag_unchanged_returns_cache_hit(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    """Second fetch with same ETag → cache hit; no second extraction."""

    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.adapters.crawl4ai_web import Crawl4AIAdapter

    _stub_robots(httpx_mock, "example.invalid")
    httpx_mock.add_response(
        url="https://example.invalid/page",
        status_code=200,
        headers={"Content-Type": "text/html", "ETag": '"v1"'},
        content=_FIXTURE_HTML.encode("utf-8"),
    )
    # Second request returns 304 Not Modified.
    httpx_mock.add_response(
        url="https://example.invalid/page",
        status_code=304,
    )

    adapter = Crawl4AIAdapter(
        source_tier="L2", cache_dir=tmp_path / "wc",
    )
    r1 = asyncio.run(adapter.fetch_url("https://example.invalid/page"))
    r2 = asyncio.run(adapter.fetch_url("https://example.invalid/page"))

    assert r1.cache_hit is False
    assert r2.cache_hit is True
    # The cached record retains the original content.
    assert r2.content_hash == r1.content_hash
    assert r2.title == r1.title


def test_content_hash_unchanged_returns_cache_hit(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    """Re-fetch returns identical body (no ETag served) → content-hash cache hit."""

    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.adapters.crawl4ai_web import Crawl4AIAdapter

    _stub_robots(httpx_mock, "example.invalid")
    httpx_mock.add_response(
        url="https://example.invalid/page",
        status_code=200,
        headers={"Content-Type": "text/html"},
        content=_FIXTURE_HTML.encode("utf-8"),
    )
    httpx_mock.add_response(
        url="https://example.invalid/page",
        status_code=200,
        headers={"Content-Type": "text/html"},
        content=_FIXTURE_HTML.encode("utf-8"),
    )

    adapter = Crawl4AIAdapter(
        source_tier="L2", cache_dir=tmp_path / "wc",
    )
    r1 = asyncio.run(adapter.fetch_url("https://example.invalid/page"))
    r2 = asyncio.run(adapter.fetch_url("https://example.invalid/page"))

    assert r1.cache_hit is False
    assert r2.cache_hit is True


# ---------------------------------------------------------------------------
# Phase 1.5 — oversized page guard
# ---------------------------------------------------------------------------


def test_oversized_page_skipped_emits_audit(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    """Pages > 50 MB are skipped + emit an `oversized_page` audit record."""

    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.adapters.crawl4ai_web import Crawl4AIAdapter, OversizedPage

    _stub_robots(httpx_mock, "example.invalid")
    # 51 MB body — over the 50 MB hard cap from ADR-019.
    big_body = b"a" * (51 * 1024 * 1024)
    httpx_mock.add_response(
        url="https://example.invalid/big",
        status_code=200,
        headers={
            "Content-Type": "text/html",
            "Content-Length": str(len(big_body)),
        },
        content=big_body,
    )

    adapter = Crawl4AIAdapter(
        source_tier="L2", cache_dir=tmp_path / "wc",
    )
    with pytest.raises(OversizedPage):
        asyncio.run(adapter.fetch_url("https://example.invalid/big"))


# ---------------------------------------------------------------------------
# Phase 1.6 — HTML <table> extraction
# ---------------------------------------------------------------------------


def test_html_table_becomes_table_record_with_cells(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    """An HTML body with <table> → CrawledRecord exposes `tables` with rows/cols/cells."""

    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.adapters.crawl4ai_web import Crawl4AIAdapter

    html_with_table = """<!DOCTYPE html><html><body><h1>NYU COA</h1>
    <table>
      <thead><tr><th>Year</th><th>Tuition</th></tr></thead>
      <tbody>
        <tr><td>2024-25</td><td>$87,000</td></tr>
        <tr><td>2023-24</td><td>$85,000</td></tr>
      </tbody>
    </table></body></html>"""

    _stub_robots(httpx_mock, "example.invalid")
    httpx_mock.add_response(
        url="https://example.invalid/page",
        status_code=200,
        headers={"Content-Type": "text/html"},
        content=html_with_table.encode("utf-8"),
    )

    adapter = Crawl4AIAdapter(
        source_tier="L2", cache_dir=tmp_path / "wc",
    )
    record = asyncio.run(adapter.fetch_url("https://example.invalid/page"))
    assert len(record.tables) == 1
    table = record.tables[0]
    # 2 data rows × 2 cols; header preserved separately
    assert table.rows == 2
    assert table.cols == 2
    assert table.cells == [["2024-25", "$87,000"], ["2023-24", "$85,000"]]
