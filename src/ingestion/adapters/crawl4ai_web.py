"""V1.6a — `Crawl4AIAdapter` per ADR-019.

Wraps an HTTP fetcher behind the V1 `SourceAdapter` Protocol shape +
adds a high-level `fetch_url(url) -> CrawledRecord` for the website-crawl
DataSource. Honors robots.txt absolutely, enforces a non-empty UA env
var at startup, dedupes via ETag / Last-Modified / content-hash, and
dispatches by MIME (HTML / PDF / Excel / image / `<table>`).

The fetcher is injectable so tests can use ``httpx.AsyncClient`` with
``pytest-httpx``; production uses crawl4ai's ``AsyncWebCrawler`` (wired
in a tiny adapter shim — see ``_DefaultHttpxFetcher`` below). The split
keeps the adapter unit-testable without standing up Playwright Chromium
for every test.

This module does NOT import Trafilatura (per ``known-issues.md`` §1 — the
GPL boundary stays outside SecBrain's process). Main-content extraction
on HTML falls back to the V1 ``L2HtmlAdapter`` regex strip; the user can
shell out to ``trafilatura`` via the ``TRAFILATURA_SUBPROCESS_BIN`` env
var if they want richer extraction. That subprocess wiring is a
follow-up phase (L1 entity-tagged flow uses it; the adapter itself is
deliberately simple).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx

from src.ingestion.adapters._content_hash_cache import (
    CacheMeta,
    ContentHashCache,
    content_hash,
)
from src.ingestion.adapters._robots_cache import (
    RobotsCache,
    RobotsRules,
    fqdn_of,
    parse_robots_txt,
)
from src.ingestion.adapters.l2_html import L2HtmlAdapter
from src.ingestion.adapters.proxy_scrapingbee import (
    FallbackPolicy,
    ScrapingBeeFallback,
    detect_anti_bot,
)

# ---------------------------------------------------------------------------
# Constants per ADR-019
# ---------------------------------------------------------------------------

#: Hard cap on a single page body in bytes — pages over this are skipped.
MAX_PAGE_BYTES: int = 50 * 1024 * 1024  # 50 MB

#: Hard cap on a single PDF body in bytes.
MAX_PDF_BYTES: int = 100 * 1024 * 1024  # 100 MB

#: User-agent env var; refused empty at startup.
USER_AGENT_ENV: str = "CRAWL4AI_USER_AGENT"

#: Recognized HTML content-type prefixes.
_HTML_MIME_PREFIXES: tuple[str, ...] = ("text/html", "application/xhtml+xml")

#: PDF content-type.
_PDF_MIME: str = "application/pdf"

#: Excel / CSV content-types.
_EXCEL_MIMES: frozenset[str] = frozenset({
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/csv",
})


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class OversizedPage(Exception):
    """Raised when a page body exceeds the per-MIME hard cap.

    Callers should write an `oversized_page` audit row and continue with
    the next URL — this is a per-page skip, not a per-domain failure.
    """


class RobotsDisallowed(Exception):
    """Raised when an attempted fetch hits a robots.txt Disallow."""


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TableRecord:
    """One HTML `<table>` block extracted from a Page body."""

    ordinal: int
    rows: int
    cols: int
    cells: list[list[str]]
    caption: str | None = None


@dataclass(frozen=True)
class CrawledRecord:
    """One normalized record for one fetched URL.

    The DataSource layer aggregates many of these into an `IngestResult`.
    """

    url: str
    domain: str
    mime: str
    title: str
    body_md: str
    content_hash: str
    bytes_: int
    fetched_at: datetime
    source_tier: Literal["L1", "L2"]
    etag: str | None = None
    last_modified: str | None = None
    via_proxy: bool = False
    cache_hit: bool = False
    tables: list[TableRecord] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Fetcher Protocol — injectable so tests can stub HTTP
# ---------------------------------------------------------------------------


class AsyncFetcher(Protocol):
    """Minimal async HTTP surface the adapter consumes."""

    async def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> FetcherResponse: ...


@dataclass(frozen=True)
class FetcherResponse:
    """The fetcher's contract — independent of httpx / crawl4ai specifics."""

    status_code: int
    headers: dict[str, str]
    content: bytes
    via_proxy: bool = False

    def header(self, name: str) -> str | None:
        # Case-insensitive header lookup.
        target = name.lower()
        for k, v in self.headers.items():
            if k.lower() == target:
                return v
        return None


def _ProxyResponse(
    *, status_code: int, headers: dict[str, str], content: bytes,
) -> FetcherResponse:
    """Build a FetcherResponse with `via_proxy=True` set."""

    return FetcherResponse(
        status_code=status_code,
        headers=headers,
        content=content,
        via_proxy=True,
    )


class _DefaultHttpxFetcher:
    """Production fetcher — direct httpx with the SecBrain UA pinned."""

    def __init__(self, user_agent: str, *, timeout: float = 30.0) -> None:
        self._user_agent = user_agent
        self._timeout = timeout

    async def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> FetcherResponse:
        merged = {"User-Agent": self._user_agent}
        if headers:
            merged.update(headers)
        async with httpx.AsyncClient(
            timeout=timeout or self._timeout,
            follow_redirects=True,
        ) as client:
            r = await client.get(url, headers=merged)
        return FetcherResponse(
            status_code=r.status_code,
            headers=dict(r.headers),
            content=r.content,
        )


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class Crawl4AIAdapter:
    """Behind-V1-SourceAdapter wrapper around an HTTP fetcher.

    The adapter is intentionally testable without crawl4ai or Playwright
    by accepting an injectable `fetcher`. Production wiring (the
    `WebsiteCrawlSource` in Phase 3) builds one with crawl4ai's
    AsyncWebCrawler as the fetcher.
    """

    source_tier: Literal["L1", "L2"]

    def __init__(
        self,
        *,
        source_tier: Literal["L1", "L2"] = "L2",
        cache_dir: Path,
        fetcher: AsyncFetcher | None = None,
        robots_cache: RobotsCache | None = None,
        user_agent: str | None = None,
        fallback: ScrapingBeeFallback | None = None,
        fallback_policy: FallbackPolicy | None = None,
    ) -> None:
        # NFR-1.6a-6: refuse to start without a non-empty UA. The env var
        # is the source of truth; tests can override via the explicit
        # `user_agent=` kwarg to keep test-scoped overrides obvious.
        resolved_ua = user_agent if user_agent is not None else os.environ.get(USER_AGENT_ENV, "")
        if not resolved_ua or not resolved_ua.strip():
            raise RuntimeError(
                f"{USER_AGENT_ENV} must be a non-empty honest UA string "
                f"(e.g. 'SecBrain/1.6 (+contact@example.com)'). "
                "The website-crawl adapter refuses to start anonymously "
                "per NFR-1.6a-6 politeness contract.",
            )
        self._user_agent = resolved_ua.strip()
        self.source_tier = source_tier

        cache_root = Path(cache_dir)
        cache_root.mkdir(parents=True, exist_ok=True)
        self._content_cache = ContentHashCache(cache_root / "pages")
        self._robots_cache = robots_cache or RobotsCache(cache_root / "robots")
        self._fetcher: AsyncFetcher = fetcher or _DefaultHttpxFetcher(self._user_agent)
        # ScrapingBee opt-in: present in `fallback` AND enabled in policy.
        # Without both, the adapter never consults the proxy regardless of
        # detection signals. ADR-019 §3.
        self._fallback = fallback
        self._fallback_policy = fallback_policy or FallbackPolicy(enabled=False)
        # Per-domain failure counter — keyed on FQDN. Reset on success
        # or fallback invocation.
        self._consecutive_failures: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Robots.txt API
    # ------------------------------------------------------------------

    async def is_allowed_by_robots(self, url: str) -> bool:
        """True if robots.txt allows fetching `url` for our UA.

        404 / network failure on robots.txt → treated as "all allowed"
        per RFC 9309 default. Cached at `robots_cache`.
        """

        rules = await self._get_or_fetch_robots(url)
        if rules is None:
            return True
        path = httpx.URL(url).path or "/"
        return rules.is_allowed(path)

    async def crawl_delay(self, url: str) -> float | None:
        """Crawl-delay clamped to the 0.5-10s politeness range, or None."""

        rules = await self._get_or_fetch_robots(url)
        if rules is None:
            return None
        return rules.clamped_crawl_delay()

    async def _get_or_fetch_robots(self, url: str) -> RobotsRules | None:
        fqdn = fqdn_of(url)
        if not fqdn:
            return None
        cached = self._robots_cache.get(fqdn)
        now = datetime.now(UTC)
        if cached and not cached.is_expired(now):
            return cached
        robots_url = f"https://{fqdn}/robots.txt"
        try:
            response = await self._fetcher.get(robots_url, timeout=10.0)
        except Exception:
            # Network failure → treat as no rules (RFC 9309 default-allow).
            return None
        if response.status_code == 404:
            # No robots.txt → all allowed. Cache an empty ruleset so we
            # don't re-fetch within the TTL.
            empty = parse_robots_txt("", now=now)
            self._robots_cache.put(fqdn, empty)
            return empty
        if response.status_code >= 400:
            # Other failures → don't cache; allow this fetch.
            return None
        rules = parse_robots_txt(response.content.decode("utf-8", "replace"), now=now)
        self._robots_cache.put(fqdn, rules)
        return rules

    # ------------------------------------------------------------------
    # Per-URL fetch
    # ------------------------------------------------------------------

    async def fetch_url(self, url: str) -> CrawledRecord:
        """Fetch + dispatch + cache one URL.

        Raises:
            RobotsDisallowed: robots.txt forbids this URL.
            OversizedPage: body exceeds the per-MIME hard cap.
            httpx.HTTPError: network / response error from the fetcher.
        """

        if not await self.is_allowed_by_robots(url):
            raise RobotsDisallowed(url)

        # Pre-fetch conditional-GET: send If-None-Match / If-Modified-Since
        # so the server can return 304 cheaply.
        prior_meta = self._content_cache.get_meta(url)
        conditional: dict[str, str] = {}
        if prior_meta:
            if prior_meta.etag:
                conditional["If-None-Match"] = prior_meta.etag
            if prior_meta.last_modified:
                conditional["If-Modified-Since"] = prior_meta.last_modified

        response = await self._attempt_with_fallback(
            url=url,
            headers=conditional or None,
            prior_meta=prior_meta,
        )
        if response.status_code == 304 and prior_meta:
            cached_body = self._content_cache.get_body(url, mime=prior_meta.mime)
            if cached_body is not None:
                return self._normalize(
                    url=url,
                    body=cached_body,
                    mime=prior_meta.mime,
                    etag=prior_meta.etag,
                    last_modified=prior_meta.last_modified,
                    fetched_at=prior_meta.fetched_at,
                    cache_hit=True,
                    via_proxy=False,
                )

        if response.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{url} returned {response.status_code}",
                request=httpx.Request("GET", url),
                response=httpx.Response(response.status_code, content=response.content),
            )

        mime = (response.header("Content-Type") or "application/octet-stream").split(
            ";", 1,
        )[0].strip().lower()
        body = response.content
        self._enforce_size_caps(body=body, mime=mime, url=url)

        etag = response.header("ETag")
        last_modified = response.header("Last-Modified")
        body_hash = content_hash(body)
        fetched_at = datetime.now(UTC)

        # Content-hash cache hit: if the body is byte-identical to what we
        # already have, treat as cache hit (no extraction re-cost).
        cache_hit = bool(prior_meta and prior_meta.content_hash == body_hash)

        # Write through to disk only when content changed (or new).
        if not cache_hit:
            self._content_cache.put(
                body=body,
                meta=CacheMeta(
                    url=url,
                    etag=etag,
                    last_modified=last_modified,
                    content_hash=body_hash,
                    bytes_=len(body),
                    mime=mime,
                    fetched_at=fetched_at,
                ),
            )

        return self._normalize(
            url=url,
            body=body,
            mime=mime,
            etag=etag,
            last_modified=last_modified,
            fetched_at=fetched_at if not cache_hit else (prior_meta.fetched_at if prior_meta else fetched_at),
            cache_hit=cache_hit,
            via_proxy=getattr(response, "via_proxy", False),
        )

    def get_cached_body(self, url: str, *, mime: str) -> bytes | None:
        """Raw cached body for `url` (or None). Used by the crawl worker
        to extract links/images from HTML without a second fetch."""

        return self._content_cache.get_body(url, mime=mime)

    # ------------------------------------------------------------------
    # Fallback orchestration
    # ------------------------------------------------------------------

    async def _attempt_with_fallback(
        self,
        *,
        url: str,
        headers: dict[str, str] | None,
        prior_meta: CacheMeta | None,
    ) -> FetcherResponse:
        """Local fetch with retry; consult ScrapingBee when the policy says so.

        Two triggers per ADR-019:
        1. N consecutive 403/429/503 within this call — try the local
           fetcher up to N times; if all fail, fall back to the proxy.
        2. Anti-bot challenge detected in a 200 response — fall back
           immediately (no retry wait).
        """

        max_retries = max(1, self._fallback_policy.consecutive_failures_to_trigger)
        primary: FetcherResponse | None = None
        for _attempt in range(max_retries):
            primary = await self._fetcher.get(url, headers=headers)
            if primary.status_code in {403, 429, 503}:
                # Retry inside the same fetch_url call up to N times.
                continue
            # Anti-bot detection short-circuit on 2xx
            if primary.status_code < 400 and detect_anti_bot(
                headers=primary.headers, body=primary.content,
            ):
                break
            return primary

        # All retries exhausted (or anti-bot detected) — try the fallback.
        if self._fallback is not None and self._fallback_policy.enabled:
            bee = await self._fallback.fetch(
                url,
                user_agent=self._user_agent,
                render_js=self._fallback_policy.render_js,
                premium_proxy=self._fallback_policy.premium_proxy,
                country_code=self._fallback_policy.country_code,
            )
            return _ProxyResponse(
                status_code=bee.status_code,
                headers=bee.headers,
                content=bee.content,
            )

        # No fallback configured / disabled — return the last primary
        # response (caller will raise HTTPStatusError on its 4xx).
        assert primary is not None
        return primary

    # ------------------------------------------------------------------
    # Normalization (per-MIME dispatch)
    # ------------------------------------------------------------------

    def _normalize(
        self,
        *,
        url: str,
        body: bytes,
        mime: str,
        etag: str | None,
        last_modified: str | None,
        fetched_at: datetime,
        cache_hit: bool,
        via_proxy: bool = False,
    ) -> CrawledRecord:
        title, body_md, tables = self._extract(mime=mime, body=body)
        return CrawledRecord(
            url=url,
            domain=fqdn_of(url),
            mime=mime,
            title=title,
            body_md=body_md,
            content_hash=content_hash(body),
            bytes_=len(body),
            fetched_at=fetched_at,
            source_tier=self.source_tier,
            etag=etag,
            last_modified=last_modified,
            via_proxy=via_proxy,
            cache_hit=cache_hit,
            tables=tables,
        )

    def _extract(
        self, *, mime: str, body: bytes,
    ) -> tuple[str, str, list[TableRecord]]:
        if any(mime.startswith(p) for p in _HTML_MIME_PREFIXES):
            return self._extract_html(body)
        if mime == _PDF_MIME:
            return self._extract_pdf(body)
        if mime in _EXCEL_MIMES:
            return self._extract_excel(body, mime=mime)
        if mime.startswith("image/"):
            # Images: no body text; OCR is handled in L1 flow, not the
            # adapter itself (per FR-1.6a-2.4 + NFR-1.6a-7 cache layout).
            return ("", "", [])
        # Unknown MIME: keep the bytes, no extraction.
        return ("", "", [])

    @staticmethod
    def _extract_html(body: bytes) -> tuple[str, str, list[TableRecord]]:
        html_text = body.decode("utf-8", "replace")
        doc = L2HtmlAdapter().parse_string(html_text)
        tables = _extract_html_tables(html_text)
        return (doc.title, doc.body, tables)

    #: Hard cap on PDF pages we run text extraction over (cost guard).
    MAX_PDF_TEXT_PAGES: int = 300
    #: Hard cap on spreadsheet rows materialized per sheet (memory guard).
    MAX_SHEET_ROWS: int = 5_000

    @staticmethod
    def _extract_pdf(body: bytes) -> tuple[str, str, list[TableRecord]]:
        """Title via pikepdf metadata + full body text via pypdf.

        Official L1 sources publish their ground truth as PDFs (e.g. NMS
        match statistics); without body text the downstream L1 flow can't
        chunk or entity-tag them, so the adapter extracts text here.
        """

        title = ""
        try:
            import pikepdf  # noqa: PLC0415
            with pikepdf.open(BytesIO(body)) as pdf:
                docinfo: dict[str, object] = dict(pdf.docinfo) if pdf.docinfo else {}
                title_obj = docinfo.get("/Title")
                title = str(title_obj) if title_obj else ""
        except Exception:
            title = ""

        body_md = ""
        try:
            from pypdf import PdfReader  # noqa: PLC0415
            reader = PdfReader(BytesIO(body))
            parts: list[str] = []
            for page in reader.pages[:Crawl4AIAdapter.MAX_PDF_TEXT_PAGES]:
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""
                if text.strip():
                    parts.append(text)
            body_md = "\n\n".join(parts)
        except Exception:
            body_md = ""
        return (title, body_md, [])

    @staticmethod
    def _extract_excel(
        body: bytes, *, mime: str,
    ) -> tuple[str, str, list[TableRecord]]:
        """Parse XLSX/XLS/CSV bytes into TableRecords (one per sheet).

        ADEA / ADA-HPI publish per-school ground truth as XLSX — these
        tables ARE the L1 payload, so they must land as Table nodes.
        `body_md` carries a small sheet summary so the Page node is
        searchable; the cell payload lives on the Table nodes.
        """

        try:
            import pandas as pd  # noqa: PLC0415
        except ImportError:
            return ("", "", [])

        max_rows = Crawl4AIAdapter.MAX_SHEET_ROWS
        frames: list[tuple[str, Any]] = []
        try:
            if mime == "text/csv":
                frames = [("csv", pd.read_csv(BytesIO(body), nrows=max_rows))]
            else:
                sheets = pd.read_excel(BytesIO(body), sheet_name=None, nrows=max_rows)
                frames = list(sheets.items())
        except Exception:
            return ("", "", [])

        tables: list[TableRecord] = []
        summary_lines: list[str] = []
        for idx, (sheet_name, df) in enumerate(frames):
            if df.empty:
                continue
            header = [str(c) for c in df.columns]
            cells: list[list[str]] = [header] + [
                [_cell_to_str(v) for v in row] for row in df.itertuples(index=False)
            ]
            tables.append(TableRecord(
                ordinal=idx,
                rows=len(cells),
                cols=len(header),
                cells=cells,
                caption=str(sheet_name),
            ))
            summary_lines.append(
                f"sheet '{sheet_name}': {len(df)} rows x {len(header)} cols "
                f"({', '.join(header[:12])})"
            )
        return ("", "\n".join(summary_lines), tables)

    # ------------------------------------------------------------------
    # Size guards
    # ------------------------------------------------------------------

    @staticmethod
    def _enforce_size_caps(*, body: bytes, mime: str, url: str) -> None:
        if mime == _PDF_MIME and len(body) > MAX_PDF_BYTES:
            raise OversizedPage(f"{url} PDF body {len(body)} > {MAX_PDF_BYTES}")
        if len(body) > MAX_PAGE_BYTES:
            raise OversizedPage(f"{url} body {len(body)} > {MAX_PAGE_BYTES}")


# ---------------------------------------------------------------------------
# HTML table extraction helper (kept module-level for testability)
# ---------------------------------------------------------------------------


def _extract_html_tables(html: str) -> list[TableRecord]:
    """Parse `<table>` blocks from `html` into TableRecord list.

    Uses `pandas.read_html` per ADR-019; falls back to an empty list on
    parse failure. Header rows are excluded from the cell count; the
    `rows`/`cols` counts reflect the data area.
    """

    if "<table" not in html.lower():
        return []
    # Local import: pandas is pulled in transitively by V1; we keep
    # the import in-function so HTML pages without tables don't trigger
    # the import cost.
    try:
        import pandas as pd  # noqa: PLC0415
    except ImportError:
        return []

    try:
        dfs = pd.read_html(StringIO(html))
    except (ValueError, ImportError):
        return []

    tables: list[TableRecord] = []
    for idx, df in enumerate(dfs):
        if df.empty:
            continue
        cells: list[list[str]] = [
            [_cell_to_str(v) for v in row] for row in df.itertuples(index=False)
        ]
        tables.append(TableRecord(
            ordinal=idx,
            rows=len(cells),
            cols=len(cells[0]) if cells else 0,
            cells=cells,
            caption=None,
        ))
    return tables


def _cell_to_str(value: Any) -> str:
    # Local import — mirrors _extract_html_tables; avoids forcing pandas
    # at module-import time.
    import pandas as pd  # noqa: PLC0415
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value)


__all__ = [
    "MAX_PAGE_BYTES",
    "MAX_PDF_BYTES",
    "USER_AGENT_ENV",
    "AsyncFetcher",
    "Crawl4AIAdapter",
    "CrawledRecord",
    "FetcherResponse",
    "OversizedPage",
    "RobotsDisallowed",
    "TableRecord",
]
