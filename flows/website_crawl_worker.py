"""V1.7 — production crawl worker: the missing glue per the Wiring Gate.

Everything around it existed (registry, dispatcher, adapter, L0/L1/L2
flows) but nothing composed them — `WebsiteCrawlDispatcher`'s `worker`
param was only ever a test stub, so a UI "Run now" enqueued a row that
nothing consumed. This module is that worker:

    discover URLs (robots sitemaps -> sitemap.xml -> BFS fallback)
    -> Crawl4AIAdapter.fetch_url per URL (robots, cache, politeness)
    -> link/image extraction from cached HTML
    -> run_l0_for_domain (Page/Table/MediaAsset/ExternalRef nodes)
    -> run_l1_for_domain (chunks + entity tags, stage >= L1)
    -> run_l2_for_domain (budget-gated LLM summaries, stage == L2,
       only when a summarizer is injected)
    -> crawl_fetch_log + pages_index + crawl_jobs counters

Use `make_worker(...)` to bind a WorkerFn for the dispatcher, or
`crawl_domain_once(...)` to run one domain synchronously (CLI path).
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urldefrag, urljoin, urlparse

from flows.website_crawl_dispatcher import spent_this_month
from flows.website_l0_sitemap import run_l0_for_domain
from flows.website_l1_entity_tagged import run_l1_for_domain
from flows.website_l2_full_graphrag import L2Summarizer, run_l2_for_domain
from src.ingestion.adapters.crawl4ai_web import (
    Crawl4AIAdapter,
    CrawledRecord,
    OversizedPage,
    RobotsDisallowed,
    _DefaultHttpxFetcher,
)
from src.ingestion.sources.website_crawl import (
    CrawlDomainRow,
    WebsiteCrawlRegistry,
)

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

#: Politeness floor between fetches when robots.txt has no Crawl-delay.
DEFAULT_CRAWL_DELAY_S: float = 0.5

#: Sitemap recursion guards.
MAX_SITEMAP_DEPTH: int = 3
MAX_SUB_SITEMAPS: int = 50

#: File extensions never worth fetching as Pages (assets, archives, media).
#: PDFs / spreadsheets are deliberately NOT here — official L1 data lives
#: in them.
_SKIP_EXTENSIONS: frozenset[str] = frozenset({
    ".css", ".js", ".mjs", ".map", ".ico", ".woff", ".woff2", ".ttf",
    ".eot", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif",
    ".mp3", ".mp4", ".mov", ".avi", ".webm", ".zip", ".gz", ".tar",
    ".rar", ".7z", ".dmg", ".exe", ".msi", ".apk", ".jar",
})

_LOC_RE = re.compile(r"<loc>\s*([^<]+?)\s*</loc>", re.IGNORECASE)
_SITEMAPINDEX_RE = re.compile(r"<\s*sitemapindex[\s>]", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CrawlRunReport:
    """Everything one worker run produced (also returned as a dict)."""

    status: str
    pages_discovered: int
    pages_fetched: int
    pages_unchanged: int
    pages_skipped_robots: int
    pages_skipped_size: int
    pages_errored: int
    cost_usd: float
    l0_pages_written: int
    l1_chunks_written: int
    l1_mentions_written: int
    l2_summaries_written: int
    discovery_mode: str
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "pages_discovered": self.pages_discovered,
            "pages_fetched": self.pages_fetched,
            "pages_unchanged": self.pages_unchanged,
            "pages_skipped_robots": self.pages_skipped_robots,
            "pages_skipped_size": self.pages_skipped_size,
            "pages_errored": self.pages_errored,
            "cost_usd": self.cost_usd,
            "l0_pages_written": self.l0_pages_written,
            "l1_chunks_written": self.l1_chunks_written,
            "l1_mentions_written": self.l1_mentions_written,
            "l2_summaries_written": self.l2_summaries_written,
            "discovery_mode": self.discovery_mode,
            "note": self.note,
        }


# ---------------------------------------------------------------------------
# URL discovery
# ---------------------------------------------------------------------------


def _same_site(url: str, domain: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    domain = domain.lower()
    bare = domain[4:] if domain.startswith("www.") else domain
    return host == domain or host == bare or host.endswith("." + bare)


def _crawlable(url: str, domain: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    if not _same_site(url, domain):
        return False
    path = parsed.path.lower()
    return not any(path.endswith(ext) for ext in _SKIP_EXTENSIONS)


def _normalize_url(url: str) -> str:
    return urldefrag(url.strip())[0]


async def _fetch_text(fetcher: _DefaultHttpxFetcher, url: str) -> str | None:
    try:
        response = await fetcher.get(url, timeout=20.0)
    except Exception:
        return None
    if response.status_code >= 400:
        return None
    return response.content.decode("utf-8", "replace")


async def _discover_via_sitemaps(
    *,
    fetcher: _DefaultHttpxFetcher,
    adapter: Crawl4AIAdapter,
    domain: str,
    cap: int,
) -> list[str]:
    """Robots-declared sitemaps first, then conventional locations."""

    rules = await adapter._get_or_fetch_robots(f"https://{domain}/")  # noqa: SLF001
    candidates: list[str] = list(rules.sitemaps) if rules and rules.sitemaps else []
    candidates += [
        f"https://{domain}/sitemap.xml",
        f"https://{domain}/sitemap_index.xml",
    ]

    urls: list[str] = []
    seen_urls: set[str] = set()
    seen_sitemaps: set[str] = set()

    async def walk(sitemap_url: str, depth: int) -> None:
        if depth > MAX_SITEMAP_DEPTH or len(seen_sitemaps) >= MAX_SUB_SITEMAPS:
            return
        if sitemap_url in seen_sitemaps or len(urls) >= cap:
            return
        seen_sitemaps.add(sitemap_url)
        text = await _fetch_text(fetcher, sitemap_url)
        if not text or "<" not in text:
            return
        locs = [loc.strip() for loc in _LOC_RE.findall(text)]
        if _SITEMAPINDEX_RE.search(text):
            for loc in locs:
                await walk(loc, depth + 1)
            return
        for loc in locs:
            if len(urls) >= cap:
                return
            normalized = _normalize_url(loc)
            if normalized in seen_urls or not _crawlable(normalized, domain):
                continue
            seen_urls.add(normalized)
            urls.append(normalized)

    for candidate in candidates:
        await walk(candidate, depth=0)
        if urls:
            break
    return urls


def _extract_links_and_images(
    *, base_url: str, html_body: bytes,
) -> tuple[list[str], list[str]]:
    """Absolute same-or-cross-domain link + image URLs from raw HTML."""

    try:
        from lxml import html as lxml_html  # noqa: PLC0415
        tree = lxml_html.fromstring(html_body)
    except Exception:
        return ([], [])
    links: list[str] = []
    images: list[str] = []
    seen_l: set[str] = set()
    seen_i: set[str] = set()
    for href in tree.xpath("//a/@href"):
        absolute = _normalize_url(urljoin(base_url, str(href)))
        if urlparse(absolute).scheme in ("http", "https") and absolute not in seen_l:
            seen_l.add(absolute)
            links.append(absolute)
    for src in tree.xpath("//img/@src"):
        absolute = _normalize_url(urljoin(base_url, str(src)))
        if urlparse(absolute).scheme in ("http", "https") and absolute not in seen_i:
            seen_i.add(absolute)
            images.append(absolute)
    return (links, images)


# ---------------------------------------------------------------------------
# Fetch loop
# ---------------------------------------------------------------------------


@dataclass
class _FetchOutcome:
    records: list[tuple[CrawledRecord, list[str], list[str]]]
    unchanged: int
    skipped_robots: int
    skipped_size: int
    errored: int
    proxy_fetches: int


async def _fetch_all(
    *,
    adapter: Crawl4AIAdapter,
    urls: list[str],
    domain: CrawlDomainRow,
    job_id: str,
    sqlite_path: Path,
    bfs_mode: bool,
    cap: int,
    progress: Callable[[str], None],
) -> _FetchOutcome:
    """Fetch `urls` sequentially with politeness; BFS-extends when asked."""

    outcome = _FetchOutcome(
        records=[], unchanged=0, skipped_robots=0,
        skipped_size=0, errored=0, proxy_fetches=0,
    )
    queue: list[str] = list(urls)
    visited: set[str] = set()

    while queue and len(outcome.records) < cap:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        started = time.monotonic()
        error_note: str | None = None
        record: CrawledRecord | None = None
        try:
            record = await adapter.fetch_url(url)
        except RobotsDisallowed:
            outcome.skipped_robots += 1
            error_note = "robots_disallowed"
        except OversizedPage as exc:
            outcome.skipped_size += 1
            error_note = f"oversized: {exc}"[:200]
        except Exception as exc:  # network / HTTP / parse failures
            outcome.errored += 1
            error_note = str(exc)[:200]
        latency_ms = int((time.monotonic() - started) * 1000)

        links: list[str] = []
        images: list[str] = []
        if record is not None:
            if record.cache_hit:
                outcome.unchanged += 1
            if record.via_proxy:
                outcome.proxy_fetches += 1
            if record.mime.startswith("text/html"):
                raw = adapter.get_cached_body(url, mime=record.mime)
                if raw:
                    links, images = _extract_links_and_images(
                        base_url=url, html_body=raw,
                    )
                if bfs_mode:
                    for link in links:
                        if (
                            link not in visited
                            and _crawlable(link, domain.domain)
                            and len(queue) + len(outcome.records) < cap * 3
                        ):
                            queue.append(link)
            outcome.records.append((record, links, images))

        _write_fetch_log(
            sqlite_path=sqlite_path,
            job_id=job_id,
            domain_id=domain.domain_id,
            url=url,
            record=record,
            latency_ms=latency_ms,
            error=error_note,
        )
        if len(outcome.records) % 25 == 0 and record is not None:
            progress(
                f"[crawl:{domain.domain}] {len(outcome.records)}/{cap} pages "
                f"({outcome.unchanged} unchanged, {outcome.errored} errors)",
            )

        delay = await adapter.crawl_delay(url)
        await asyncio.sleep(delay if delay is not None else DEFAULT_CRAWL_DELAY_S)

    return outcome


# ---------------------------------------------------------------------------
# SQLite bookkeeping
# ---------------------------------------------------------------------------


def _write_fetch_log(
    *,
    sqlite_path: Path,
    job_id: str,
    domain_id: str,
    url: str,
    record: CrawledRecord | None,
    latency_ms: int,
    error: str | None,
) -> None:
    with sqlite3.connect(sqlite_path) as conn:
        conn.execute(
            "INSERT INTO crawl_fetch_log (fetch_id, job_id, domain_id, url, "
            "mime, status_code, etag, last_modified, content_hash, bytes, "
            "fetched_at, via_proxy, cost_usd, latency_ms, cache_hit, error_excerpt) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"fetch:{uuid.uuid4().hex[:16]}",
                job_id,
                domain_id,
                url,
                record.mime if record else None,
                200 if record else None,
                record.etag if record else None,
                record.last_modified if record else None,
                record.content_hash if record else None,
                record.bytes_ if record else None,
                datetime.now(UTC).isoformat(),
                int(record.via_proxy) if record else 0,
                0.0,
                latency_ms,
                int(record.cache_hit) if record else 0,
                error,
            ),
        )
        conn.commit()


def _upsert_pages_index(
    *,
    sqlite_path: Path,
    domain_id: str,
    records: list[tuple[CrawledRecord, list[str], list[str]]],
    l1_ran: bool,
) -> None:
    from src.graph.web_node_types import page_node_id  # noqa: PLC0415

    now_iso = datetime.now(UTC).isoformat()
    with sqlite3.connect(sqlite_path) as conn:
        for record, _links, _images in records:
            node_id = page_node_id(url=record.url, content_hash=record.content_hash)
            row = conn.execute(
                "SELECT page_index_id, last_content_hash, version_count "
                "FROM pages_index WHERE domain_id = ? AND url = ?",
                (domain_id, record.url),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO pages_index (page_index_id, domain_id, url, "
                    "graph_node_id, mime, first_seen_at, last_seen_at, "
                    "last_content_hash, last_etag, last_last_modified, "
                    "version_count, stage_l1_done_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
                    (
                        f"pidx:{uuid.uuid4().hex[:16]}",
                        domain_id,
                        record.url,
                        node_id,
                        record.mime,
                        now_iso,
                        now_iso,
                        record.content_hash,
                        record.etag,
                        record.last_modified,
                        now_iso if l1_ran else None,
                    ),
                )
            else:
                bumped = int(row[2]) + (0 if row[1] == record.content_hash else 1)
                conn.execute(
                    "UPDATE pages_index SET graph_node_id = ?, mime = ?, "
                    "last_seen_at = ?, last_content_hash = ?, last_etag = ?, "
                    "last_last_modified = ?, version_count = ?, "
                    "stage_l1_done_at = COALESCE(?, stage_l1_done_at) "
                    "WHERE page_index_id = ?",
                    (
                        node_id,
                        record.mime,
                        now_iso,
                        record.content_hash,
                        record.etag,
                        record.last_modified,
                        bumped,
                        now_iso if l1_ran else None,
                        row[0],
                    ),
                )
        conn.commit()


def _update_job_counters(
    *, sqlite_path: Path, job_id: str, report: CrawlRunReport,
) -> None:
    with sqlite3.connect(sqlite_path) as conn:
        conn.execute(
            "UPDATE crawl_jobs SET pages_discovered = ?, pages_unchanged = ?, "
            "pages_skipped_robots = ?, pages_skipped_size = ?, pages_blocked = ? "
            "WHERE job_id = ?",
            (
                report.pages_discovered,
                report.pages_unchanged,
                report.pages_skipped_robots,
                report.pages_skipped_size,
                0,
                job_id,
            ),
        )
        conn.commit()


def _pages_fetched_this_month(
    *, sqlite_path: Path, domain_id: str, now: datetime,
) -> int:
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    with sqlite3.connect(sqlite_path) as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(pages_fetched), 0) FROM crawl_jobs "
            "WHERE domain_id = ? AND finished_at >= ?",
            (domain_id, month_start.isoformat()),
        ).fetchone()
    return int(row[0]) if row else 0


# ---------------------------------------------------------------------------
# The worker
# ---------------------------------------------------------------------------


def crawl_domain_once(
    domain_id: str,
    job_id: str,
    *,
    sqlite_path: Path,
    graph: Any,
    cache_dir: Path,
    summarizer: L2Summarizer | None = None,
    max_pages_override: int | None = None,
    progress: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Run one full crawl for `domain_id`. Returns the dispatcher dict."""

    registry = WebsiteCrawlRegistry(sqlite_path=sqlite_path)
    domain = registry.get(domain_id)
    if domain is None:
        raise ValueError(f"unknown crawl domain '{domain_id}'")

    now = datetime.now(UTC)
    month_used = _pages_fetched_this_month(
        sqlite_path=sqlite_path, domain_id=domain_id, now=now,
    )
    month_left = max(0, domain.max_pages_per_month - month_used)
    cap = min(max_pages_override or domain.max_pages_per_run, month_left)
    if cap <= 0:
        report = CrawlRunReport(
            status="capped", pages_discovered=0, pages_fetched=0,
            pages_unchanged=0, pages_skipped_robots=0, pages_skipped_size=0,
            pages_errored=0, cost_usd=0.0, l0_pages_written=0,
            l1_chunks_written=0, l1_mentions_written=0,
            l2_summaries_written=0, discovery_mode="none",
            note=f"monthly page cap reached ({month_used}/{domain.max_pages_per_month})",
        )
        _update_job_counters(sqlite_path=sqlite_path, job_id=job_id, report=report)
        return report.as_dict()

    adapter = Crawl4AIAdapter(
        source_tier=domain.tier,
        cache_dir=Path(cache_dir) / domain.domain,
    )
    sitemap_fetcher = _DefaultHttpxFetcher(adapter._user_agent)  # noqa: SLF001

    async def _run() -> tuple[list[str], str, _FetchOutcome]:
        urls = await _discover_via_sitemaps(
            fetcher=sitemap_fetcher, adapter=adapter,
            domain=domain.domain, cap=cap,
        )
        mode = "sitemap"
        if not urls:
            urls = [f"https://{domain.domain}/"]
            mode = "bfs"
        progress(
            f"[crawl:{domain.domain}] discovery={mode} "
            f"urls={len(urls)} cap={cap}",
        )
        outcome = await _fetch_all(
            adapter=adapter, urls=urls, domain=domain, job_id=job_id,
            sqlite_path=sqlite_path, bfs_mode=(mode == "bfs"), cap=cap,
            progress=progress,
        )
        return urls, mode, outcome

    discovered, mode, outcome = asyncio.run(_run())

    # ---- L0: Page / Table / MediaAsset / ExternalRef nodes -------------
    l0 = run_l0_for_domain(
        domain=domain, records=outcome.records, graph=graph, job_id=job_id,
    )

    # ---- L1: chunks + entity tags --------------------------------------
    l1_chunks = 0
    l1_mentions = 0
    l1_ran = False
    if domain.stage in ("L1", "L2"):
        from src.er.canonical_index import CanonicalIndex  # noqa: PLC0415
        canonical = CanonicalIndex(sqlite_path)
        l1 = run_l1_for_domain(
            domain=domain,
            records=[record for record, _l, _i in outcome.records],
            graph=graph, canonical=canonical, job_id=job_id,
        )
        l1_chunks = l1.chunks_written
        l1_mentions = l1.mentions_written
        l1_ran = True

    # ---- L2: budget-gated cluster summaries (needs a summarizer) -------
    l2_summaries = 0
    cost_usd = 0.0
    note = ""
    if domain.stage == "L2":
        if summarizer is None:
            note = "L2 stage requested but no summarizer wired; ran L0+L1 only"
        else:
            spent = spent_this_month(
                sqlite_path=sqlite_path, domain_id=domain_id, now=now,
            )
            l2 = run_l2_for_domain(
                domain=domain,
                records=[record for record, _l, _i in outcome.records],
                graph=graph, summarizer=summarizer, job_id=job_id,
                spent_so_far_usd=spent,
            )
            l2_summaries = getattr(l2, "summaries_written", 0)
            cost_usd += getattr(l2, "cost_usd", 0.0)
            if getattr(l2, "cap_hit", False) or l2.__class__.__name__ == "L2BudgetCapped":
                note = "L2 budget cap hit"

    _upsert_pages_index(
        sqlite_path=sqlite_path, domain_id=domain_id,
        records=outcome.records, l1_ran=l1_ran,
    )

    report = CrawlRunReport(
        status="succeeded",
        pages_discovered=len(discovered),
        pages_fetched=len(outcome.records),
        pages_unchanged=outcome.unchanged,
        pages_skipped_robots=outcome.skipped_robots,
        pages_skipped_size=outcome.skipped_size,
        pages_errored=outcome.errored,
        cost_usd=cost_usd,
        l0_pages_written=l0.pages_written,
        l1_chunks_written=l1_chunks,
        l1_mentions_written=l1_mentions,
        l2_summaries_written=l2_summaries,
        discovery_mode=mode,
        note=note,
    )
    _update_job_counters(sqlite_path=sqlite_path, job_id=job_id, report=report)
    progress(
        f"[crawl:{domain.domain}] done: {report.pages_fetched} fetched, "
        f"{report.l0_pages_written} pages written, {l1_chunks} chunks, "
        f"{l1_mentions} mentions ({mode})",
    )
    return report.as_dict()


def make_worker(
    *,
    sqlite_path: Path,
    graph: Any,
    cache_dir: Path,
    summarizer: L2Summarizer | None = None,
    progress: Callable[[str], None] = print,
) -> Callable[[str, str], dict[str, Any]]:
    """Bind a `WorkerFn` for `WebsiteCrawlDispatcher(worker=...)`."""

    def worker(domain_id: str, job_id: str) -> dict[str, Any]:
        return crawl_domain_once(
            domain_id, job_id,
            sqlite_path=sqlite_path, graph=graph, cache_dir=cache_dir,
            summarizer=summarizer, progress=progress,
        )

    return worker


__all__ = [
    "CrawlRunReport",
    "crawl_domain_once",
    "make_worker",
]
