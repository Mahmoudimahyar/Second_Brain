"""Tests for `src.ingestion.sources.base.DataSource` Protocol (V1.5a FR-1.5a-1)."""

from __future__ import annotations

from typing import get_type_hints

from src.ingestion.sources.base import (
    CursorState,
    DataSource,
    LocalFileConfig,
    SchemaSnapshot,
    SourceManifest,
)


def test_protocol_is_importable() -> None:
    """Importing the Protocol exercises its module's top-level statements."""
    assert DataSource is not None


def test_source_manifest_pydantic_shape() -> None:
    """Manifest must serialize cleanly so V1.5b Zod can mirror it."""
    manifest = SourceManifest(
        source_id="ds:local_file:test",
        engine="local_file",
        display_name="Test fixture",
        config=LocalFileConfig(adapter="l5_reddit", paths=["/tmp/x.jsonl"]),
        tier="L5",
        credential_ref=None,
        notes=None,
    )
    payload = manifest.model_dump_json()
    assert "ds:local_file:test" in payload
    assert "l5_reddit" in payload


def test_cursor_state_serialisable() -> None:
    """Cursor state must survive sqlite TEXT round-trip."""
    cursor = CursorState(
        cursor_table=None,
        cursor_column="content_hash",
        cursor_value="abc123",
    )
    revived = CursorState.model_validate_json(cursor.model_dump_json())
    assert revived == cursor


def test_protocol_signatures_present() -> None:
    """Every DataSource concrete must expose the V1.5a contract surface."""
    # The Protocol is purely declarative — we assert the runtime-checkable
    # interface lists the FR-1.5a-1.1 methods.
    methods = {"open", "close", "discover_schema", "sample_rows",
               "pull_delta", "manifest"}
    protocol_attrs = set(dir(DataSource))
    missing = methods - protocol_attrs
    assert not missing, f"DataSource Protocol missing: {missing}"


def test_schema_snapshot_round_trip() -> None:
    snap = SchemaSnapshot(
        source_id="ds:local_file:test",
        discovered_at=__import__("datetime").datetime.now(
            __import__("datetime").UTC,
        ),
        tables=[],
        labels=[],
        rel_types=[],
    )
    revived = SchemaSnapshot.model_validate_json(snap.model_dump_json())
    assert revived.source_id == snap.source_id


def test_get_type_hints_resolves() -> None:
    """All Pydantic models must have resolvable type hints (pyright sanity)."""
    for model in (SourceManifest, SchemaSnapshot, CursorState):
        # Should not raise — failure here usually means a string-forward-ref
        # didn't resolve.
        get_type_hints(model)
