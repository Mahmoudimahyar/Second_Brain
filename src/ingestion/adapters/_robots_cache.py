"""V1.6a — RFC 9309 robots.txt cache for the website-crawl adapter.

Per ADR-019: robots.txt is fetched once per crawl run + cached. TTL is the
`max-age` directive from response headers, or 24h, whichever is shorter.
Disallow rules are honored absolutely (no override). `Crawl-delay` is
clamped to the 0.5-10 s politeness range.

The on-disk format is a plain JSON file per FQDN under the adapter's
cache directory; this is intentionally simple — there's at most one row
per domain and reads happen at most once per crawl. SQLite would be
overkill.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

# Per ADR-019 §"Per-domain budget" politeness range.
_CRAWL_DELAY_MIN_S: float = 0.5
_CRAWL_DELAY_MAX_S: float = 10.0
_DEFAULT_TTL_S: int = 86_400  # 24h
_USER_AGENT_TOKEN: str = "*"


@dataclass(frozen=True)
class RobotsRules:
    """Parsed robots.txt directives for one FQDN.

    `allow_paths` and `disallow_paths` apply to `User-agent: *`. The
    longest-matching directive wins per RFC 9309 §5.2.
    """

    fetched_at: datetime
    expires_at: datetime
    allow_paths: list[str] = field(default_factory=list)
    disallow_paths: list[str] = field(default_factory=list)
    crawl_delay_s: float | None = None
    sitemaps: list[str] = field(default_factory=list)

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def is_allowed(self, path: str) -> bool:
        """RFC 9309 §5.2: longest-match wins; Allow beats Disallow on tie."""

        path = path or "/"
        best_match_len = -1
        verdict = True  # default-allow when no rule matches
        for rule, allowed in self._all_rules():
            if not rule:
                continue
            if path.startswith(rule):
                if len(rule) > best_match_len:
                    best_match_len = len(rule)
                    verdict = allowed
                elif len(rule) == best_match_len and allowed:
                    # Allow beats Disallow on equal-length match.
                    verdict = True
        return verdict

    def _all_rules(self) -> list[tuple[str, bool]]:
        return [(p, True) for p in self.allow_paths] + [
            (p, False) for p in self.disallow_paths
        ]

    def clamped_crawl_delay(self) -> float | None:
        if self.crawl_delay_s is None:
            return None
        return max(_CRAWL_DELAY_MIN_S, min(_CRAWL_DELAY_MAX_S, self.crawl_delay_s))


class RobotsCache:
    """File-backed robots.txt cache, one JSON file per FQDN.

    Tests can inject an in-memory variant by subclassing or by routing
    `cache_dir` into a `tmp_path`. The cache is intentionally per-instance
    (no global singletons) so the adapter can be safely instantiated in
    parallel test runs.
    """

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, fqdn: str) -> RobotsRules | None:
        path = self._path_for(fqdn)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return RobotsRules(
            fetched_at=datetime.fromisoformat(payload["fetched_at"]),
            expires_at=datetime.fromisoformat(payload["expires_at"]),
            allow_paths=list(payload.get("allow_paths") or []),
            disallow_paths=list(payload.get("disallow_paths") or []),
            crawl_delay_s=payload.get("crawl_delay_s"),
            sitemaps=list(payload.get("sitemaps") or []),
        )

    def put(self, fqdn: str, rules: RobotsRules) -> None:
        path = self._path_for(fqdn)
        path.write_text(
            json.dumps(
                {
                    "fetched_at": rules.fetched_at.isoformat(),
                    "expires_at": rules.expires_at.isoformat(),
                    "allow_paths": rules.allow_paths,
                    "disallow_paths": rules.disallow_paths,
                    "crawl_delay_s": rules.crawl_delay_s,
                    "sitemaps": rules.sitemaps,
                },
                indent=None,
            ),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _path_for(self, fqdn: str) -> Path:
        # FQDN is a-z 0-9 . - so safe in a filename; lowercase to dedupe.
        return self._cache_dir / f"{fqdn.lower()}.json"


def parse_robots_txt(body: str, *, now: datetime | None = None) -> RobotsRules:
    """Minimal RFC 9309 parser sufficient for ADR-019 politeness contract.

    We only honor `User-agent: *` rules + the global `Sitemap:` lines.
    Per-vendor User-agent groups (e.g. `User-agent: SecBrain`) are not
    used in V1.6a — our honest UA discloses contact email; we treat ourselves
    as a generic bot. The 24 h default TTL applies; if the response carries
    `Cache-Control: max-age=N` the caller can pass that via the wrapping
    fetcher and adjust `expires_at`.
    """

    now = now or datetime.now(UTC)
    allow_paths: list[str] = []
    disallow_paths: list[str] = []
    crawl_delay: float | None = None
    sitemaps: list[str] = []

    current_agent: str | None = None
    for raw_line in body.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            continue
        directive, _, value = line.partition(":")
        directive = directive.strip().lower()
        value = value.strip()
        if directive == "user-agent":
            current_agent = value.lower() or "*"
        elif directive == "sitemap":
            sitemaps.append(value)
        elif current_agent in (_USER_AGENT_TOKEN, None):
            # Globally-scoped lines (no User-agent yet) and `User-agent: *`
            # both feed into the same allow/disallow set.
            if directive == "allow" and value:
                allow_paths.append(value)
            elif directive == "disallow" and value:
                disallow_paths.append(value)
            elif directive == "crawl-delay":
                try:
                    crawl_delay = float(value)
                except ValueError:
                    crawl_delay = None

    return RobotsRules(
        fetched_at=now,
        expires_at=now + timedelta(seconds=_DEFAULT_TTL_S),
        allow_paths=allow_paths,
        disallow_paths=disallow_paths,
        crawl_delay_s=crawl_delay,
        sitemaps=sitemaps,
    )


def fqdn_of(url: str) -> str:
    """`https://www.adea.org/foo` → `www.adea.org`."""

    parsed = urlparse(url)
    return (parsed.hostname or "").lower()


__all__ = ["RobotsCache", "RobotsRules", "fqdn_of", "parse_robots_txt"]
