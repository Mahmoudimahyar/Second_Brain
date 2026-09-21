"""Tests for `src.ingestion.api.IngestionService.register_dump` (FR-1.1)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.ingestion.api import DumpManifest, DumpReceipt, IngestionService
from src.shared.errors import ErrorCode, StructuredError


def _write_payload(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _make_manifest(
    source_tier: str = "L1", source_name: str = "test_source",
) -> DumpManifest:
    return DumpManifest(
        source_name=source_name,
        source_tier=source_tier,  # type: ignore[arg-type]
        rank_default="preferred",
        license="test license",
        t_valid_range=(
            datetime(2020, 1, 1, tzinfo=UTC),
            datetime(2024, 12, 31, tzinfo=UTC),
        ),
    )


def _make_service(tmp_path: Path) -> IngestionService:
    return IngestionService(
        dumps_root=tmp_path / "dumps",
        sqlite_path=tmp_path / "sqlite" / "store.db",
    )


def test_register_dump_returns_receipt_with_content_hashes(tmp_path: Path) -> None:
    payload = _write_payload(tmp_path, "data.csv", "school,year,tuition\nNYU,2024,90000\n")
    service = _make_service(tmp_path)

    receipt = service.register_dump("L1", _make_manifest(), [payload])

    assert isinstance(receipt, DumpReceipt)
    assert receipt.source_tier == "L1"
    assert receipt.validation_result == "ok"
    assert receipt.duplicate_of is None
    assert len(receipt.content_hashes) == 1
    assert len(receipt.content_hashes[0]) == 64
    assert receipt.dump_id.startswith("dump:")
    assert receipt.t_ingest_from.tzinfo is not None


def test_register_dump_copies_payload_to_immutable_store(tmp_path: Path) -> None:
    payload = _write_payload(tmp_path, "data.csv", "x")
    service = _make_service(tmp_path)

    service.register_dump("L1", _make_manifest(), [payload])

    assert payload.exists()
    copies = list((tmp_path / "dumps").rglob("data.csv"))
    assert len(copies) == 1
    assert copies[0].read_text(encoding="utf-8") == "x"


def test_register_dump_idempotent_on_identical_payloads(tmp_path: Path) -> None:
    payload = _write_payload(tmp_path, "data.csv", "y")
    service = _make_service(tmp_path)

    first = service.register_dump("L1", _make_manifest(), [payload])
    second = service.register_dump("L1", _make_manifest(), [payload])

    assert first.dump_id == second.dump_id
    assert first.duplicate_of is None
    assert second.duplicate_of == first.dump_id

    copies = list((tmp_path / "dumps").rglob("data.csv"))
    assert len(copies) == 1


def test_register_dump_distinguishes_different_payloads(tmp_path: Path) -> None:
    a = _write_payload(tmp_path, "a.csv", "alpha")
    b = _write_payload(tmp_path, "b.csv", "beta")
    service = _make_service(tmp_path)

    receipt_a = service.register_dump("L1", _make_manifest(), [a])
    receipt_b = service.register_dump("L1", _make_manifest(), [b])

    assert receipt_a.dump_id != receipt_b.dump_id
    assert receipt_a.content_hashes != receipt_b.content_hashes


def test_register_dump_distinguishes_source_tiers_with_identical_bytes(
    tmp_path: Path,
) -> None:
    payload = _write_payload(tmp_path, "shared.csv", "same-bytes")
    service = _make_service(tmp_path)

    r_l1 = service.register_dump("L1", _make_manifest("L1"), [payload])
    r_l5 = service.register_dump("L5", _make_manifest("L5"), [payload])

    assert r_l1.dump_id != r_l5.dump_id
    assert r_l1.content_hashes == r_l5.content_hashes


def test_register_dump_rejects_tier_mismatch(tmp_path: Path) -> None:
    payload = _write_payload(tmp_path, "x.csv", "1")
    service = _make_service(tmp_path)
    manifest = _make_manifest(source_tier="L1")

    with pytest.raises(StructuredError) as exc:
        service.register_dump("L5", manifest, [payload])
    assert exc.value.error_code == ErrorCode.INGESTION_MANIFEST_INVALID


def test_register_dump_rejects_missing_payload(tmp_path: Path) -> None:
    service = _make_service(tmp_path)
    with pytest.raises(StructuredError) as exc:
        service.register_dump("L1", _make_manifest(), [tmp_path / "nope.csv"])
    assert exc.value.error_code == ErrorCode.INGESTION_PAYLOAD_MISSING


def test_register_dump_rejects_empty_payload_list(tmp_path: Path) -> None:
    service = _make_service(tmp_path)
    with pytest.raises(StructuredError) as exc:
        service.register_dump("L1", _make_manifest(), [])
    assert exc.value.error_code == ErrorCode.INGESTION_PAYLOAD_MISSING


def test_content_hash_stable_across_service_instances(tmp_path: Path) -> None:
    payload = _write_payload(tmp_path, "x.csv", "stable-content")

    service_a = _make_service(tmp_path / "a")
    service_b = _make_service(tmp_path / "b")

    receipt_a = service_a.register_dump("L1", _make_manifest(), [payload])
    receipt_b = service_b.register_dump("L1", _make_manifest(), [payload])

    assert receipt_a.content_hashes == receipt_b.content_hashes
    assert receipt_a.dump_id == receipt_b.dump_id


def test_manifest_rejects_empty_source_name() -> None:
    with pytest.raises(ValidationError):
        DumpManifest(
            source_name="",
            source_tier="L1",
            rank_default="preferred",
            license="test",
            t_valid_range=(
                datetime(2020, 1, 1, tzinfo=UTC),
                datetime(2024, 12, 31, tzinfo=UTC),
            ),
        )


def test_register_dump_persists_to_sqlite(tmp_path: Path) -> None:
    payload = _write_payload(tmp_path, "data.csv", "row\n")
    service = _make_service(tmp_path)

    receipt = service.register_dump("L1", _make_manifest(), [payload])

    conn = sqlite3.connect(tmp_path / "sqlite" / "store.db")
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM dump WHERE dump_id = ?", (receipt.dump_id,),
    ).fetchone()
    conn.close()

    assert row is not None
    assert row["source_tier"] == "L1"
    assert row["source_name"] == "test_source"
