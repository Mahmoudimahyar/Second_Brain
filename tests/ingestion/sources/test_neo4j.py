"""Unit tests for `Neo4jDataSource` using a mock driver.

Real-Neo4j integration tests with testcontainers live in
`test_neo4j_integration.py` (skipped when Docker is unavailable).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest

from src.ingestion.sources.base import Neo4jConfig, SourceManifest
from src.ingestion.sources.neo4j import Neo4jDataSource
from src.shared.errors import ErrorCode, StructuredError


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def __iter__(self) -> Iterable[Any]:
        for r in self._rows:
            class _Rec:
                def __init__(self, d: dict[str, Any]) -> None:
                    self._d = d

                def data(self) -> dict[str, Any]:
                    return self._d

                def __getitem__(self, key: str) -> Any:
                    return self._d[key]
            yield _Rec(r)


class _FakeSession:
    def __init__(self, scripted: dict[str, list[dict[str, Any]]]) -> None:
        self._scripted = scripted

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def run(self, cypher: str, **kwargs: Any) -> _FakeResult:
        for key, rows in self._scripted.items():
            if key in cypher:
                return _FakeResult(rows)
        return _FakeResult([])


class _FakeDriver:
    def __init__(self, scripted: dict[str, list[dict[str, Any]]]) -> None:
        self._scripted = scripted

    def session(self, database: str | None = None) -> _FakeSession:
        return _FakeSession(self._scripted)

    def close(self) -> None:
        pass


def _manifest(credential_ref: str | None = None) -> SourceManifest:
    return SourceManifest(
        source_id="ds:neo4j:test",
        engine="neo4j",
        display_name="Test Neo4j",
        config=Neo4jConfig(uri="bolt://localhost:7687", user="neo4j"),
        tier="L2",
        credential_ref=credential_ref,
    )


def test_credentials_required_raises_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MY_NEO_PW", raising=False)
    ds = Neo4jDataSource(
        _manifest("MY_NEO_PW"),
        connect_factory=lambda cfg, pw: _FakeDriver({}),
    )
    with pytest.raises(StructuredError) as excinfo:
        ds.open()
    assert excinfo.value.error_code == ErrorCode.CRED_NOT_FOUND


def test_credentials_present_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_NEO_PW", "neo4jpass")
    ds = Neo4jDataSource(
        _manifest("MY_NEO_PW"),
        connect_factory=lambda cfg, pw: _FakeDriver({}),
    )
    ds.open()
    assert ds.is_open()
    ds.close()


def test_discover_labels_and_rel_types() -> None:
    scripted = {
        "db.labels()": [{"label": "School"}, {"label": "Program"}],
        "db.relationshipTypes()": [
            {"relationshipType": "OFFERS_PROGRAM"},
        ],
        "MATCH (n:`School`)": [{"n": {"id": "s1", "name": "NYU"}}],
        "MATCH (n:`Program`)": [{"n": {"id": "p1", "name": "Endo"}}],
    }
    ds = Neo4jDataSource(
        _manifest(), connect_factory=lambda cfg, pw: _FakeDriver(scripted),
    )
    with ds:
        snap = ds.discover_schema()
    assert {lab.name for lab in snap.labels} == {"School", "Program"}
    assert {rt.name for rt in snap.rel_types} == {"OFFERS_PROGRAM"}


def test_connect_failure_wrapped() -> None:
    def _bad(cfg: Neo4jConfig, pw: str | None) -> _FakeDriver:
        raise RuntimeError("ServiceUnavailable")
    ds = Neo4jDataSource(_manifest(), connect_factory=_bad)
    with pytest.raises(StructuredError) as excinfo:
        ds.open()
    assert excinfo.value.error_code == ErrorCode.CONNECTION_FAILED


def test_apoc_optional_path_falls_back_gracefully() -> None:
    """If APOC is not installed, discovery returns whatever the standard
    procedures yield. Mock returns empty for both → empty snapshot."""
    ds = Neo4jDataSource(
        _manifest(), connect_factory=lambda cfg, pw: _FakeDriver({}),
    )
    with ds:
        snap = ds.discover_schema()
    assert snap.labels == []
    assert snap.rel_types == []
