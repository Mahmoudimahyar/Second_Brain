"""V1.6a — Hard blocklist for the website-crawl source.

Per ADR-019 §"Domain blocklist": forum + social-media domains cannot be
registered as a V1.6a `WebsiteCrawlSource`. Forums have their own
ingestion path (V1 Reddit/SDN, V1.6b Discord/Discourse/Stack Exchange);
social media is permanently out of scope.

Per AGENTS.md "Human approval required": the contents of this file are
a security-relevant action. Additions / removals require Mahyar's
sign-off in a commit message + an entry in
`docs/00-bootstrap/unresolved-questions.md` if the change is non-trivial.
The current seed list is the one ratified at V1.6a kickoff (2026-05-27).

Subdomain semantics: a domain is blocked if it is OR is a subdomain of
any entry in FORUM_DOMAINS or SOCIAL_DOMAINS (union of the two sets).
So `old.reddit.com` is blocked because `reddit.com` is in the set;
`notreddit.com` is NOT blocked because `reddit.com` is not its suffix.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Seed lists (per ADR-019 §"Domain blocklist", ratified 2026-05-27)
# ---------------------------------------------------------------------------

#: Forum-type domains. V1 Reddit/SDN adapters cover Reddit + SDN today;
#: V1.6b will add Discord / Discourse / Stack Exchange. Crawl-path
#: registration is rejected so users don't accidentally re-ingest those
#: corpora via the wrong path.
FORUM_DOMAINS: frozenset[str] = frozenset({
    "reddit.com", "old.reddit.com",
    "studentdoctor.net", "sdn.net",
    "stackoverflow.com", "stackexchange.com",
    "discord.com", "discord.gg",
    "discourse.org", "discoursehosting.com",
})

#: Social-media domains. Permanently out of scope (no V1.x path).
SOCIAL_DOMAINS: frozenset[str] = frozenset({
    "twitter.com", "x.com",
    "instagram.com", "facebook.com",
    "linkedin.com", "tiktok.com",
    "snapchat.com", "youtube.com",
    "bsky.app", "mastodon.social",
    "threads.net", "pinterest.com",
})


def _normalize(domain: str) -> str:
    """Lowercase + strip protocol/path; "https://reddit.com/foo" -> "reddit.com"."""

    d = (domain or "").strip().lower()
    # Strip protocol if accidentally included
    for prefix in ("https://", "http://"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    # Strip any path / query / port
    for sep in ("/", "?", "#", ":"):
        idx = d.find(sep)
        if idx >= 0:
            d = d[:idx]
    return d


def is_blocked(domain: str) -> bool:
    """True if `domain` matches or is a subdomain of any blocked entry.

    Matching rule per ADR-019: `old.reddit.com` is blocked because
    `reddit.com` is in the set. `notreddit.com` is NOT blocked because
    `reddit.com` is not a suffix of `notreddit.com` after the dot-prefix
    requirement.
    """

    d = _normalize(domain)
    if not d:
        return False
    blocked_set = FORUM_DOMAINS | SOCIAL_DOMAINS
    if d in blocked_set:
        return True
    return any(d.endswith("." + entry) for entry in blocked_set)


def block_reason(domain: str) -> str | None:
    """Human-readable reason + pointer for a blocked domain, or None."""

    d = _normalize(domain)
    if not d:
        return None
    matched_entry: str | None = None
    for entry in FORUM_DOMAINS | SOCIAL_DOMAINS:
        if d == entry or d.endswith("." + entry):
            matched_entry = entry
            break
    if matched_entry is None:
        return None
    if matched_entry in FORUM_DOMAINS:
        return (
            f"'{d}' is a forum domain. Forums have their own ingestion path: "
            "the V1 Reddit adapter handles reddit.com / old.reddit.com; "
            "the V1 SDN adapter handles studentdoctor.net; "
            "V1.6b will add Discord / Discourse / Stack Exchange. "
            "The website-crawl path is for official sites only."
        )
    return (
        f"'{d}' is a social-media domain. Social media is out of scope for "
        "SecBrain's crawler (no V1.x roadmap path). If you have a public "
        "snapshot of relevant content from this source, upload it via the "
        "V1 manual-dump path instead."
    )


__all__ = [
    "FORUM_DOMAINS",
    "SOCIAL_DOMAINS",
    "block_reason",
    "is_blocked",
]
