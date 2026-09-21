"""Tests for V1.5a Phase 4 — tier declaration + L1 immutability enforcement.

Covers AC-4 + AC-6 from `docs/05-features/02-slice-v1.5a-db-connector/README.md`
and FR-1.5a-4.1..4.4.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import orjson
import pytest
from pydantic import ValidationError

from src.ingestion.api import IngestionService
from src.ingestion.sources.base import LocalFileConfig, SourceManifest
from src.ingestion.sources.registry import (
    INVALID_TIER_UPGRADE,
    L1_REQUIRES_CONFIRMATION,
    MULTIPLE_L1_CLAIMS,
    DataSourceRegistry,
    DataSourceRow,
)
from src.shared.errors import ErrorCode, StructuredError


@pytest.fixture
def reddit_fixture(tmp_path: Path) -> Path:
    path = tmp_path / "x_posts.jsonl"
    with path.open("wb") as f:
        f.write(orjson.dumps({
            "id": "a1",
            "name": "t3_a1",
            "author": "u1",
            "created_utc": 1_700_000_000,
            "title": "t",
            "selftext": "",
            "subreddit": "x",
            "subreddit_id": "t5_x",
            "score": 1,
            "ups": 1,
            "downs": 0,
            "num_comments": 0,
            "link_flair_text": None,
            "permalink": "/r/x/comments/a1/_",
            "url": "https://example.org/",
            "over_18": False,
        }))
        f.write(b"\n")
    return path


@pytest.fixture
def registry(tmp_path: Path) -> DataSourceRegistry:
    return DataSourceRegistry(sqlite_path=tmp_path / "engine.db")


def _manifest(
    reddit_fixture: Path, *, tier: str = "L2", source_id: str = "ds:t",
) -> SourceManifest:
    return SourceManifest(
        source_id=source_id,
        engine="local_file",
        display_name="Test",
        config=LocalFileConfig(adapter="l5_reddit", paths=[str(reddit_fixture)]),
        tier=tier,  # type: ignore[arg-type]
        credential_ref=None,
        notes=None,
    )


# AC-4 — Tier declaration enforcement -------------------------------------


def test_default_tier_is_l2(registry: DataSourceRegistry, reddit_fixture: Path) -> None:
    """FR-1.5a-4.1 — `SourceManifest.tier` defaults to L2."""
    manifest = SourceManifest(
        source_id="ds:default",
        engine="local_file",
        display_name="D",
        config=LocalFileConfig(adapter="l5_reddit", paths=[str(reddit_fixture)]),
    )
    assert manifest.tier == "L2"
    row = registry.register(manifest, actor="user", confirm_l1_immutable=False)
    assert row.tier == "L2"


def test_l1_without_confirmation_rejected(
    registry: DataSourceRegistry, reddit_fixture: Path,
) -> None:
    """FR-1.5a-4.2 — tier=L1 without confirm_l1_immutable raises."""
    manifest = _manifest(reddit_fixture, tier="L1", source_id="ds:l1_no_conf")
    with pytest.raises(StructuredError) as excinfo:
        registry.register(manifest, actor="user", confirm_l1_immutable=False)
    assert excinfo.value.error_code == ErrorCode.L1_IMMUTABLE_REJECT
    assert L1_REQUIRES_CONFIRMATION in str(excinfo.value)


def test_l1_with_confirmation_accepted(
    registry: DataSourceRegistry, reddit_fixture: Path,
) -> None:
    manifest = _manifest(reddit_fixture, tier="L1", source_id="ds:l1_ok")
    row = registry.register(manifest, actor="user", confirm_l1_immutable=True)
    assert row.tier == "L1"
    assert row.l1_confirmed_at is not None
    assert row.l1_confirmed_at.tzinfo is not None


def test_invalid_tier_value_rejected(reddit_fixture: Path) -> None:
    """Manifest with an unknown tier should fail Pydantic validation."""
    with pytest.raises(ValidationError):
        SourceManifest(
            source_id="ds:bad",
            engine="local_file",
            display_name="bad",
            config=LocalFileConfig(adapter="l5_reddit", paths=[str(reddit_fixture)]),
            tier="L6",  # type: ignore[arg-type]
        )


def test_audit_log_records_l1_upgrade_attempt(
    registry: DataSourceRegistry, reddit_fixture: Path,
) -> None:
    """FR-1.5a-8.1 — every L1 attempt audit-logged (accepted or rejected)."""
    manifest = _manifest(reddit_fixture, tier="L1", source_id="ds:audit_l1")
    with pytest.raises(StructuredError):
        registry.register(
            manifest, actor="user", confirm_l1_immutable=False,
        )
    # And the accepted path:
    registry.register(
        manifest, actor="user", confirm_l1_immutable=True,
    )

    rows = registry.audit_log_entries(kind="connector_tier_upgrade_attempt")
    assert len(rows) == 2
    rejected = [r for r in rows if r["outcome"] == "rejected"]
    accepted = [r for r in rows if r["outcome"] == "accepted"]
    assert len(rejected) == 1
    assert len(accepted) == 1


def test_retier_closes_old_tingest_to(
    registry: DataSourceRegistry, reddit_fixture: Path,
) -> None:
    """FR-1.5a-4.3 — changing tier closes the prior `t_ingest_to` and opens
    a new range. Inspectable via registry.tier_history(source_id).
    """
    manifest = _manifest(reddit_fixture, tier="L2", source_id="ds:retier")
    registry.register(manifest, actor="user")
    history_before = registry.tier_history("ds:retier")
    assert len(history_before) == 1
    assert history_before[-1].tier == "L2"
    assert history_before[-1].t_ingest_to is None

    registry.retier(
        source_id="ds:retier",
        new_tier="L1",
        actor="user",
        confirm_l1_immutable=True,
    )
    history_after = registry.tier_history("ds:retier")
    assert len(history_after) == 2
    assert history_after[0].tier == "L2"
    assert history_after[0].t_ingest_to is not None  # closed
    assert history_after[1].tier == "L1"
    assert history_after[1].t_ingest_to is None      # active


def test_retier_to_l1_without_confirmation_rejected(
    registry: DataSourceRegistry, reddit_fixture: Path,
) -> None:
    manifest = _manifest(reddit_fixture, tier="L2", source_id="ds:retier_bad")
    registry.register(manifest, actor="user")
    with pytest.raises(StructuredError) as excinfo:
        registry.retier(
            source_id="ds:retier_bad",
            new_tier="L1",
            actor="user",
            confirm_l1_immutable=False,
        )
    assert excinfo.value.error_code == ErrorCode.L1_IMMUTABLE_REJECT
    assert INVALID_TIER_UPGRADE in str(excinfo.value)


def test_register_idempotent_on_same_manifest(
    registry: DataSourceRegistry, reddit_fixture: Path,
) -> None:
    """Re-registering an existing source_id is a no-op returning the prior row."""
    manifest = _manifest(reddit_fixture, source_id="ds:idemp")
    first = registry.register(manifest, actor="user")
    second = registry.register(manifest, actor="user")
    assert first.source_id == second.source_id
    assert first.created_at == second.created_at


# AC-6 — L1 immutability + multi-L1 collision -----------------------------


def test_multi_l1_collision_raises_structured(
    registry: DataSourceRegistry, reddit_fixture: Path,
) -> None:
    """FR-1.5a-4.4 — two L1 sources claiming same subject is a HITL escalation,
    not auto-resolution. Registry only enforces the "two L1 connectors on
    the same subject domain" guard; per-claim resolution is later.
    """
    m1 = _manifest(reddit_fixture, tier="L1", source_id="ds:l1_first")
    m2 = _manifest(reddit_fixture, tier="L1", source_id="ds:l1_second")
    registry.register(m1, actor="user", confirm_l1_immutable=True)
    # Second L1 connector with overlapping subject — surfaces as a warning
    # row, not an exception. We assert the registry exposes a multi-L1
    # detection API used by the conflict-resolver downstream.
    registry.register(m2, actor="user", confirm_l1_immutable=True)
    multi = registry.detect_multi_l1_claims()
    assert any(MULTIPLE_L1_CLAIMS in str(m) for m in multi)


def test_tier_history_is_bitemporal(
    registry: DataSourceRegistry, reddit_fixture: Path,
) -> None:
    """The tier history is bitemporal: queryable `as_of` returns the tier
    that was active at a given time."""
    manifest = _manifest(reddit_fixture, tier="L2", source_id="ds:bitemp")
    row1 = registry.register(manifest, actor="user")
    t_before = row1.t_ingest_from
    registry.retier(
        source_id="ds:bitemp",
        new_tier="L3",
        actor="user",
    )
    # as_of before the retier returns the original tier
    as_of_old = registry.tier_as_of("ds:bitemp", at=t_before)
    assert as_of_old == "L2"
    # as_of now returns the current
    as_of_now = registry.tier_as_of("ds:bitemp", at=datetime.now(UTC))
    assert as_of_now == "L3"


def test_get_row_returns_pydantic_model(
    registry: DataSourceRegistry, reddit_fixture: Path,
) -> None:
    manifest = _manifest(reddit_fixture, source_id="ds:get")
    registry.register(manifest, actor="user")
    row = registry.get("ds:get")
    assert isinstance(row, DataSourceRow)
    assert row.source_id == "ds:get"
    assert row.status == "active"


def test_list_active_only(
    registry: DataSourceRegistry, reddit_fixture: Path,
) -> None:
    m1 = _manifest(reddit_fixture, source_id="ds:a")
    m2 = _manifest(reddit_fixture, source_id="ds:b")
    registry.register(m1, actor="user")
    registry.register(m2, actor="user")
    registry.disconnect("ds:b", actor="user")
    actives = registry.list_active()
    assert {r.source_id for r in actives} == {"ds:a"}


# IngestionService integration --------------------------------------------


def test_ingestion_service_register_data_source_persists_row(
    tmp_path: Path,
    reddit_fixture: Path,
) -> None:
    """The high-level service routes through the registry. FR-1.5a-1.2 +
    FR-1.5a-4 integration smoke."""
    service = IngestionService(
        dumps_root=tmp_path / "dumps",
        sqlite_path=tmp_path / "engine.db",
    )
    manifest = _manifest(reddit_fixture, source_id="ds:svc")
    ds = service.register_data_source(manifest)
    assert ds.source_id == "ds:svc"
    # The registry under the same sqlite must show the row.
    registry = DataSourceRegistry(sqlite_path=tmp_path / "engine.db")
    row = registry.get("ds:svc")
    assert row is not None
    assert row.engine == "local_file"
    assert row.tier == "L2"


def test_credentials_never_written(
    registry: DataSourceRegistry, reddit_fixture: Path,
) -> None:
    """NFR-1.5a-7 — credentials never persisted in registry rows."""
    manifest = SourceManifest(
        source_id="ds:nocreds",
        engine="local_file",
        display_name="N",
        config=LocalFileConfig(adapter="l5_reddit", paths=[str(reddit_fixture)]),
        tier="L5",
        credential_ref="PARTNER_DB_PASSWORD",  # ref only, never the value
    )
    registry.register(manifest, actor="user")
    row = registry.get("ds:nocreds")
    assert row is not None
    serialized = row.model_dump_json()
    # The ref is OK (it's just an env-var name); the value never is.
    assert "PARTNER_DB_PASSWORD" in serialized
    assert "supersecret" not in serialized
