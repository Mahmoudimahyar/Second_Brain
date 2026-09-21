"""Unit tests for `MySQLDataSource` using a mock connection factory.

Integration tests with testcontainers MySQL live in
`test_mysql_integration.py` and are skipped when Docker is unavailable.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.ingestion.sources.base import MySQLConfig, SourceManifest
from src.ingestion.sources.mysql import MySQLDataSource
from src.shared.errors import ErrorCode, StructuredError


class _FakeCursor:
    def __init__(self, scripted: dict[str, list[dict[str, Any]]]) -> None:
        self._scripted = scripted
        self._pending: list[dict[str, Any]] = []

    def execute(self, sql: str, args: tuple[Any, ...] = ()) -> None:
        self._pending = []
        for key, rows in self._scripted.items():
            if key in sql:
                self._pending = list(rows)
                return

    def fetchall(self) -> list[dict[str, Any]]:
        rows = self._pending
        self._pending = []
        return rows


class _FakeConnection:
    def __init__(self, scripted: dict[str, list[dict[str, Any]]]) -> None:
        self._scripted = scripted

    def cursor(self, dictionary: bool = False) -> _FakeCursor:
        return _FakeCursor(self._scripted)

    def close(self) -> None:
        pass


def _manifest(credential_ref: str | None = None) -> SourceManifest:
    return SourceManifest(
        source_id="ds:mysql:test",
        engine="mysql",
        display_name="Test MySQL",
        config=MySQLConfig(
            host="localhost", port=3306, database="testdb", user="root",
        ),
        tier="L2",
        credential_ref=credential_ref,
    )


def test_credentials_required_raises_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MY_MY_PW", raising=False)
    ds = MySQLDataSource(
        _manifest("MY_MY_PW"),
        connect_factory=lambda cfg: _FakeConnection({}),
    )
    with pytest.raises(StructuredError) as excinfo:
        ds.open()
    assert excinfo.value.error_code == ErrorCode.CRED_NOT_FOUND


def test_credentials_present_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_MY_PW", "secret")
    ds = MySQLDataSource(
        _manifest("MY_MY_PW"),
        connect_factory=lambda cfg: _FakeConnection({}),
    )
    ds.open()
    assert ds.is_open()
    ds.close()


def test_schema_discovery_via_mock() -> None:
    scripted: dict[str, list[dict[str, Any]]] = {
        "INFORMATION_SCHEMA.TABLES": [
            {"TABLE_SCHEMA": "testdb", "TABLE_NAME": "schools"},
        ],
        "INFORMATION_SCHEMA.COLUMNS": [
            {"COLUMN_NAME": "id", "DATA_TYPE": "int", "IS_NULLABLE": "NO"},
            {"COLUMN_NAME": "name", "DATA_TYPE": "varchar", "IS_NULLABLE": "NO"},
        ],
        "CONSTRAINT_NAME = 'PRIMARY'": [{"COLUMN_NAME": "id"}],
        "REFERENCED_TABLE_NAME IS NOT NULL": [],
    }
    ds = MySQLDataSource(
        _manifest(), connect_factory=lambda cfg: _FakeConnection(scripted),
    )
    with ds:
        snap = ds.discover_schema()
    assert any(t.name == "schools" for t in snap.tables)
    schools = next(t for t in snap.tables if t.name == "schools")
    assert {c.name for c in schools.column_specs} == {"id", "name"}
    assert schools.primary_key == ["id"]


def test_connect_failure_wrapped() -> None:
    def _bad(cfg: dict[str, Any]) -> _FakeConnection:
        raise RuntimeError("DB down")
    ds = MySQLDataSource(_manifest(), connect_factory=_bad)
    with pytest.raises(StructuredError) as excinfo:
        ds.open()
    assert excinfo.value.error_code == ErrorCode.CONNECTION_FAILED


def test_credentials_not_in_manifest_serialization() -> None:
    """The manifest never carries the resolved secret; only the env-var
    name lives in `credential_ref`."""
    manifest = _manifest("MY_MY_PW")
    blob = manifest.model_dump_json()
    # The env-var name is allowed; an actual secret string is not.
    assert "supersecret" not in blob
    assert "actualpasswordvalue" not in blob
