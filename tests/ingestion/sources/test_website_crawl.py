"""V1.6a Phase 3 — WebsiteCrawlSource + blocked_domains unit tests.

Per ADR-019 + V1.6a plan.md Phase 3. The failing-first test asserts the
forum/social blocklist refuses registration; follow-ups cover the L1
confirmation gate, cron validation, subdomain matching, and audit
write-through.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# blocked_domains module
# ---------------------------------------------------------------------------


def test_blocked_domains_forum_listed() -> None:
    from src.ingestion.sources import blocked_domains as bd

    assert "reddit.com" in bd.FORUM_DOMAINS
    assert "studentdoctor.net" in bd.FORUM_DOMAINS
    assert "stackoverflow.com" in bd.FORUM_DOMAINS
    assert "discord.com" in bd.FORUM_DOMAINS
    assert "discourse.org" in bd.FORUM_DOMAINS


def test_blocked_domains_social_listed() -> None:
    from src.ingestion.sources import blocked_domains as bd

    for d in (
        "twitter.com", "x.com", "instagram.com", "facebook.com",
        "linkedin.com", "tiktok.com", "snapchat.com", "youtube.com",
        "bsky.app", "mastodon.social", "threads.net", "pinterest.com",
    ):
        assert d in bd.SOCIAL_DOMAINS


def test_is_blocked_exact_match() -> None:
    from src.ingestion.sources import blocked_domains as bd

    assert bd.is_blocked("reddit.com") is True
    assert bd.is_blocked("twitter.com") is True
    assert bd.is_blocked("www.adea.org") is False


def test_is_blocked_subdomain_match() -> None:
    """Subdomains of blocked domains are blocked (ADR-019 §4)."""
    from src.ingestion.sources import blocked_domains as bd

    # ADR-019 explicitly mentions old.reddit.com
    assert bd.is_blocked("old.reddit.com") is True
    assert bd.is_blocked("api.twitter.com") is True
    # But a non-subdomain that contains the string is NOT blocked.
    assert bd.is_blocked("notreddit.com") is False
    assert bd.is_blocked("reddit-news.example.com") is False


def test_block_reason_returns_pointer() -> None:
    """ADR-019: registration error includes a suggestion pointer for forum domains."""
    from src.ingestion.sources import blocked_domains as bd

    reason = bd.block_reason("reddit.com")
    assert reason is not None
    assert "forum" in reason.lower() or "v1 reddit adapter" in reason.lower()

    reason_social = bd.block_reason("twitter.com")
    assert reason_social is not None
    assert "social" in reason_social.lower() or "out of scope" in reason_social.lower()

    assert bd.block_reason("adea.org") is None


# ---------------------------------------------------------------------------
# WebsiteCrawlSource — failing-first
# ---------------------------------------------------------------------------


def test_register_domain_blocked_returns_422(tmp_path: Path) -> None:
    """Failing-first per V1.6a plan.md Phase 3.

    Attempting to register `reddit.com` raises StructuredError(DOMAIN_BLOCKED).
    """

    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry
    from src.shared.errors import ErrorCode, StructuredError

    registry = WebsiteCrawlRegistry(sqlite_path=tmp_path / "engine.db")
    with pytest.raises(StructuredError) as exc:
        registry.register(
            domain="reddit.com",
            tier="L2",
            stage="L1",
            cadence_cron="0 6 * * *",
            actor="test",
        )
    assert exc.value.error_code == ErrorCode.DOMAIN_BLOCKED


# ---------------------------------------------------------------------------
# WebsiteCrawlSource follow-up tests (per plan.md Phase 3)
# ---------------------------------------------------------------------------


def test_register_domain_valid_writes_row(tmp_path: Path) -> None:
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry

    registry = WebsiteCrawlRegistry(sqlite_path=tmp_path / "engine.db")
    domain = registry.register(
        domain="www.adea.org",
        tier="L2",
        stage="L1",
        cadence_cron="0 6 * * *",
        actor="mahyar",
    )
    assert domain.domain == "www.adea.org"
    assert domain.tier == "L2"
    assert domain.stage == "L1"
    assert domain.cadence_cron == "0 6 * * *"
    assert domain.status == "active"
    assert domain.created_by == "mahyar"
    # Round-trip via the registry's get().
    fetched = registry.get(domain.domain_id)
    assert fetched is not None
    assert fetched.domain == "www.adea.org"


def test_register_domain_subdomain_of_blocked_blocked_too(tmp_path: Path) -> None:
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry
    from src.shared.errors import ErrorCode, StructuredError

    registry = WebsiteCrawlRegistry(sqlite_path=tmp_path / "engine.db")
    with pytest.raises(StructuredError) as exc:
        registry.register(
            domain="old.reddit.com",
            tier="L2",
            stage="L0",
            cadence_cron="0 6 * * *",
            actor="test",
        )
    assert exc.value.error_code == ErrorCode.DOMAIN_BLOCKED


def test_register_domain_l1_requires_confirm(tmp_path: Path) -> None:
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry
    from src.shared.errors import ErrorCode, StructuredError

    registry = WebsiteCrawlRegistry(sqlite_path=tmp_path / "engine.db")
    with pytest.raises(StructuredError) as exc:
        registry.register(
            domain="www.adea.org",
            tier="L1",
            stage="L0",
            cadence_cron="0 6 * * *",
            actor="test",
            confirm_l1_immutable=False,
        )
    assert exc.value.error_code == ErrorCode.L1_NOT_CONFIRMED


def test_register_domain_l1_with_confirm_succeeds(tmp_path: Path) -> None:
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry

    registry = WebsiteCrawlRegistry(sqlite_path=tmp_path / "engine.db")
    domain = registry.register(
        domain="www.adea.org",
        tier="L1",
        stage="L0",
        cadence_cron="0 6 * * *",
        actor="test",
        confirm_l1_immutable=True,
    )
    assert domain.tier == "L1"
    assert domain.confirm_l1 is True


def test_register_domain_invalid_cron_raises(tmp_path: Path) -> None:
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry
    from src.shared.errors import ErrorCode, StructuredError

    registry = WebsiteCrawlRegistry(sqlite_path=tmp_path / "engine.db")
    with pytest.raises(StructuredError) as exc:
        registry.register(
            domain="www.adea.org",
            tier="L2",
            stage="L0",
            cadence_cron="not a valid cron",
            actor="test",
        )
    assert exc.value.error_code == ErrorCode.INVALID_CRON


def test_register_domain_idempotent_returns_existing(tmp_path: Path) -> None:
    """Re-registering the same domain returns the existing row, not a new one."""
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry

    registry = WebsiteCrawlRegistry(sqlite_path=tmp_path / "engine.db")
    d1 = registry.register(
        domain="www.adea.org", tier="L2", stage="L1",
        cadence_cron="0 6 * * *", actor="t",
    )
    d2 = registry.register(
        domain="www.adea.org", tier="L2", stage="L1",
        cadence_cron="0 6 * * *", actor="t",
    )
    assert d1.domain_id == d2.domain_id


def test_pause_resume_round_trip(tmp_path: Path) -> None:
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry

    registry = WebsiteCrawlRegistry(sqlite_path=tmp_path / "engine.db")
    d = registry.register(
        domain="www.adea.org", tier="L2", stage="L1",
        cadence_cron="0 6 * * *", actor="t",
    )
    registry.pause(d.domain_id, actor="t")
    assert registry.get(d.domain_id).status == "paused"  # type: ignore[union-attr]
    registry.resume(d.domain_id, actor="t")
    assert registry.get(d.domain_id).status == "active"  # type: ignore[union-attr]


def test_delete_domain_soft_deletes(tmp_path: Path) -> None:
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry

    registry = WebsiteCrawlRegistry(sqlite_path=tmp_path / "engine.db")
    d = registry.register(
        domain="www.adea.org", tier="L2", stage="L1",
        cadence_cron="0 6 * * *", actor="t",
    )
    registry.delete(d.domain_id, actor="t")
    fetched = registry.get(d.domain_id)
    assert fetched is not None  # row preserved
    assert fetched.status == "deleted"


def test_list_active_excludes_deleted(tmp_path: Path) -> None:
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry

    registry = WebsiteCrawlRegistry(sqlite_path=tmp_path / "engine.db")
    a = registry.register(
        domain="adea.org", tier="L2", stage="L1",
        cadence_cron="0 6 * * *", actor="t",
    )
    b = registry.register(
        domain="ada.org", tier="L2", stage="L1",
        cadence_cron="0 6 * * *", actor="t",
    )
    registry.delete(a.domain_id, actor="t")
    active = registry.list_active()
    assert b.domain_id in {x.domain_id for x in active}
    assert a.domain_id not in {x.domain_id for x in active}
