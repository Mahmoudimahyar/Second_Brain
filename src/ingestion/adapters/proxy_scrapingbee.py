"""V1.6a — `ScrapingBeeFallback` (opt-in proxy adapter) per ADR-019.

ScrapingBee is **never the primary path**. It activates only when:

  * crawl4ai's local fetch returns 403/429/503 N consecutive times, OR
  * DataDome / PerimeterX / Cloudflare-challenge markers are detected
    in a 200 response (server returns a challenge page wearing a 200).

The proxy receives **only URL + UA + (optional) referer** per NFR-1.6a-8.
No PII, no chat history, no SecBrain-internal identifiers. SecBrain
still does its own extraction locally — ScrapingBee is treated as an
opaque HTML provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

_SCRAPINGBEE_BASE: str = "https://app.scrapingbee.com/api/v1/"

#: Per-call cost in USD — ScrapingBee's "premium proxy + JS render" tier
#: published 2025-Q4 at $0.005/req for the entry plan. The fallback writes
#: this against the per-domain budget; see ADR-019 §5.
COST_USD_PER_CALL: float = 0.005


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FallbackPolicy:
    """When and how aggressively the fallback may engage.

    Per ADR-019: domains opt in explicitly via
    ``enable_scrapingbee_fallback=True``; without that the policy must
    refuse to invoke the proxy regardless of detection signals.
    """

    enabled: bool = False
    consecutive_failures_to_trigger: int = 3
    render_js: bool = True
    premium_proxy: bool = True
    country_code: str = "us"


# ---------------------------------------------------------------------------
# Anti-bot detection (Cloudflare / DataDome / PerimeterX)
# ---------------------------------------------------------------------------


_ANTI_BOT_HEADER_MARKERS: tuple[tuple[str, str], ...] = (
    ("server", "datadome"),       # `Server: DataDome` (exact value, case-insensitive)
    ("cf-mitigated", "challenge"),
    ("server", "cloudflare"),     # Cloudflare returns this in challenge pages
)

_ANTI_BOT_COOKIE_PREFIXES: tuple[str, ...] = (
    "_pxhd=",     # PerimeterX human-difficulty hash
    "datadome=",  # DataDome cookie
)

_ANTI_BOT_BODY_MARKERS: tuple[bytes, ...] = (
    b"cf-chl-bypass",                # Cloudflare challenge token
    b"px-captcha-data",              # PerimeterX in-body marker
    b"DataDome.captchaPage()",       # DataDome injected JS
    b"Just a moment...",             # Cloudflare 5s challenge title
)


def detect_anti_bot(*, headers: dict[str, str], body: bytes) -> bool:
    """Heuristic: did the server return a challenge page wearing a 200?

    True signals an immediate fallback (skip the failure-counter wait).
    """

    # Header markers (case-insensitive)
    lowered = {k.lower(): v for k, v in (headers or {}).items()}
    for key, needle in _ANTI_BOT_HEADER_MARKERS:
        value = lowered.get(key, "").lower()
        if needle in value:
            return True

    # Cookie markers
    cookie_hdr = lowered.get("set-cookie", "")
    for prefix in _ANTI_BOT_COOKIE_PREFIXES:
        if prefix in cookie_hdr.lower():
            return True

    # Body markers — only scan first 16 KB to avoid loading whole body
    head = (body or b"")[:16_384]
    return any(marker in head for marker in _ANTI_BOT_BODY_MARKERS)


# ---------------------------------------------------------------------------
# Health-check result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HealthStatus:
    ok: bool
    status_code: int
    note: str | None = None


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------


class ScrapingBeeFallback:
    """Thin async client over the ScrapingBee API.

    Stateless — every `fetch()` builds its own httpx.AsyncClient. Cost
    accounting is the caller's responsibility (the adapter writes a
    `crawl_cost` SQLite row on each successful invocation).
    """

    def __init__(
        self,
        *,
        api_key: str,
        timeout: float = 60.0,
        base_url: str = _SCRAPINGBEE_BASE,
    ) -> None:
        if not api_key:
            raise RuntimeError(
                "ScrapingBeeFallback requires a non-empty api_key. "
                "Set SCRAPINGBEE_API_KEY in .env per ADR-019.",
            )
        self._api_key = api_key
        self._timeout = timeout
        self._base_url = base_url

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    async def fetch(
        self,
        url: str,
        *,
        user_agent: str | None = None,
        referer: str | None = None,
        render_js: bool = True,
        premium_proxy: bool = True,
        country_code: str = "us",
    ) -> ScrapingBeeResponse:
        """Fetch `url` via ScrapingBee. Returns the raw HTML + status_code.

        Per NFR-1.6a-8: only URL + UA + referer are sent. No other
        SecBrain identifiers leak through.
        """

        params = {
            "api_key": self._api_key,
            "url": url,
            "render_js": "true" if render_js else "false",
            "premium_proxy": "true" if premium_proxy else "false",
            "country_code": country_code,
        }
        # ScrapingBee accepts the UA via header on the *outgoing* fetch
        # by routing through Spb-Header-User-Agent. Keeping it in the
        # header (not the query) means we don't leak it through their
        # web-UI cost analyzer's query logs.
        forward_headers = {"Spb-Header-User-Agent": user_agent} if user_agent else {}
        if referer:
            forward_headers["Spb-Header-Referer"] = referer
        full_url = f"{self._base_url}?{urlencode(params)}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(full_url, headers=forward_headers)
        return ScrapingBeeResponse(
            status_code=r.status_code,
            headers=dict(r.headers),
            content=r.content,
            cost_usd=COST_USD_PER_CALL if r.status_code < 400 else 0.0,
        )

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health_check(self) -> HealthStatus:
        """Run a low-cost test request — render_js=false, premium=false."""

        params = {
            "api_key": self._api_key,
            "url": "https://example.com/",
            "render_js": "false",
            "premium_proxy": "false",
            "country_code": "us",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{self._base_url}?{urlencode(params)}")
        except httpx.HTTPError as exc:
            return HealthStatus(ok=False, status_code=0, note=str(exc))
        return HealthStatus(
            ok=r.status_code < 400,
            status_code=r.status_code,
            note=None if r.status_code < 400 else f"HTTP {r.status_code}",
        )


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScrapingBeeResponse:
    status_code: int
    headers: dict[str, str]
    content: bytes
    cost_usd: float


__all__ = [
    "COST_USD_PER_CALL",
    "FallbackPolicy",
    "HealthStatus",
    "ScrapingBeeFallback",
    "ScrapingBeeResponse",
    "detect_anti_bot",
]
