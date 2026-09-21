"""Unit tests for `PostgresDataSource` using a mock connection factory.

Integration tests (with testcontainers Postgres) live in
`test_postgres_integration.py` and are skipped if Docker is unavailable.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.ingestion.sources.base import (
    PostgresConfig,
    SourceManifest,
)
from src.ingestion.sources.postgres import (
    PostgresDataSource,
)
from src.shared.errors import ErrorCode, StructuredError


class _FakeCursor:
    """Mock psycopg cursor returning canned rowsets per SQL pattern."""

    def __init__(self, scripted: dict[str, list[tuple[Any, ...]]]) -> None:
        self._scripted = scripted
        self._last_sql: str = ""
        self._last_args: tuple[Any, ...] = ()
        self.description: list[tuple[Any, ...]] = []

    def execute(self, sql: str, args: tuple[Any, ...] = ()) -> None:
        self._last_sql = sql
        self._last_args = args
        # Match by substring keys in scripted so the same script can drive
        # both `information_schema` introspection AND data pulls.
        for key, rows in self._scripted.items():
            if key in sql:
                # Build a description matching the row width.
                if rows:
                    n_cols = len(rows[0])
                    self.description = [
                        (f"col_{i}", None, None, None, None, None, None)
                        for i in range(n_cols)
                    ] if not self._scripted.get(f"{key}__cols") else [
                        (c, None, None, None, None, None, None)
                        for c in self._scripted[f"{key}__cols"][0]
                    ]
                self._pending = list(rows)
                return
        self._pending = []
        self.description = []

    def fetchall(self) -> list[tuple[Any, ...]]:
        rows = self._pending
        self._pending = []
        return rows


class _FakeConnection:
    """Mock psycopg connection that hands out _FakeCursor instances."""

    def __init__(self, scripted: dict[str, list[tuple[Any, ...]]]) -> None:
        self._scripted = scripted
        self.closed = False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._scripted)

    def execute(self, sql: str, args: tuple[Any, ...] = ()) -> _FakeCursor:
        cur = _FakeCursor(self._scripted)
        cur.execute(sql, args)
        return cur

    def close(self) -> None:
        self.closed = True


def _manifest(*, credential_ref: str | None = None) -> SourceManifest:
    return SourceManifest(
        source_id="ds:postgres:test",
        engine="postgres",
        display_name="Test Postgres",
        config=PostgresConfig(
            host="localhost",
            port=5432,
            database="testdb",
            user="testuser",
        ),
        tier="L2",
        credential_ref=credential_ref,
    )


def test_credentials_required_raises_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MY_DB_PW", raising=False)
    ds = PostgresDataSource(
        _manifest(credential_ref="MY_DB_PW"),
        connect_factory=lambda dsn: _FakeConnection({}),
    )
    with pytest.raises(StructuredError) as excinfo:
        ds.open()
    assert excinfo.value.error_code == ErrorCode.CRED_NOT_FOUND


def test_credentials_present_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MY_DB_PW", "supersecret")
    ds = PostgresDataSource(
        _manifest(credential_ref="MY_DB_PW"),
        connect_factory=lambda dsn: _FakeConnection({}),
    )
    ds.open()
    assert ds.is_open()
    ds.close()


def test_credentials_explicit_arg_overrides_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MY_DB_PW", raising=False)
    ds = PostgresDataSource(
        _manifest(credential_ref="MY_DB_PW"),
        connect_factory=lambda dsn: _FakeConnection({}),
        password="explicit",
    )
    ds.open()
    assert ds.is_open()


def test_connect_failure_wrapped_in_structured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _bad_factory(dsn: str) -> _FakeConnection:
        raise OSError("ECONNREFUSED")

    ds = PostgresDataSource(
        _manifest(), connect_factory=_bad_factory,
    )
    with pytest.raises(StructuredError) as excinfo:
        ds.open()
    assert excinfo.value.error_code == ErrorCode.CONNECTION_FAILED


def test_schema_discovery_via_mock() -> None:
    """information_schema returns one table with one column."""
    scripted = {
        "information_schema.tables": [("public", "schools")],
        "information_schema.columns": [
            ("id", "integer", "NO"),
            ("name", "text", "NO"),
        ],
        "PRIMARY KEY": [("id",)],
        "FOREIGN KEY": [],
    }
    ds = PostgresDataSource(
        _manifest(), connect_factory=lambda dsn: _FakeConnection(scripted),
    )
    with ds:
        snap = ds.discover_schema()
    assert any(t.name == "schools" for t in snap.tables)
    schools = next(t for t in snap.tables if t.name == "schools")
    assert {c.name for c in schools.column_specs} == {"id", "name"}
    assert schools.primary_key == ["id"]


def test_credentials_never_in_dsn_log() -> None:
    """The DSN string should include the password if supplied, but the
    test confirms the manifest serialization (audit-log path) never
    contains it.
    """
    manifest = _manifest(credential_ref="MY_DB_PW")
    serialized = manifest.config.model_dump_json()
    # Config never carries the actual secret — only the env var name lives
    # in `credential_ref` on the manifest envelope.
    assert "supersecret" not in serialized
    # And the env-var name lives at the manifest level, not in config:
    assert "MY_DB_PW" not in serialized


def test_ssl_mode_default() -> None:
    manifest = _manifest()
    assert isinstance(manifest.config, PostgresConfig)
    assert manifest.config.ssl_mode == "prefer"
