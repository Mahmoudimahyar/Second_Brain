"""`Neo4jDataSource` — V1.5a Phase 2d engine for Neo4j (Bolt).

Uses the official `neo4j` Python driver. Schema discovery via Cypher
introspection: labels via `CALL db.labels()` + relationship types via
`CALL db.relationshipTypes()`. Treats labels as candidate node types and
rel types as candidate edge types.

APOC-optional: discovery works without APOC; per-label sample queries use
`MATCH (n:Label) RETURN n LIMIT 100`.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from types import TracebackType
from typing import Any, Protocol, cast

from src.ingestion.sources.base import (
    CanonicalRecord,
    ColumnSpec,
    CursorState,
    LabelSpec,
    Neo4jConfig,
    RelTypeSpec,
    SchemaSnapshot,
    SourceManifest,
    SourceTier,
)
from src.shared.errors import ErrorCode, StructuredError
from src.shared.timestamps import utc_now


class _Neo4jDriverProto(Protocol):
    def session(self, database: str | None = None) -> Any: ...
    def close(self) -> None: ...


ConnectFactory = Callable[[Neo4jConfig, str | None], _Neo4jDriverProto]


@dataclass
class _DiscoveredLabel:
    name: str
    sample_props: list[ColumnSpec]
    cursor_property: str | None


class Neo4jDataSource:
    """V1.5a Neo4j engine."""

    DEFAULT_SAMPLE_SIZE: int = 100

    def __init__(
        self,
        manifest: SourceManifest,
        *,
        connect_factory: ConnectFactory | None = None,
        password: str | None = None,
    ) -> None:
        if not isinstance(manifest.config, Neo4jConfig):
            raise StructuredError(
                ErrorCode.INGESTION_MANIFEST_INVALID,
                "Neo4jDataSource requires manifest.config = Neo4jConfig",
                context={"engine": manifest.engine},
            )
        self._manifest = manifest
        self._cfg: Neo4jConfig = manifest.config
        self._opened = False
        self._driver: _Neo4jDriverProto | None = None
        self._connect_factory = connect_factory or _default_neo4j_factory
        self._labels: list[_DiscoveredLabel] = []
        self._rel_types: list[str] = []
        self._last_seen_cursor: CursorState | None = None
        self._password: str | None = password
        if password is None and manifest.credential_ref:
            self._password = os.environ.get(manifest.credential_ref)

    # ------------------------------------------------------------------

    @property
    def source_id(self) -> str:
        return self._manifest.source_id

    @property
    def tier(self) -> SourceTier:
        return self._manifest.tier

    def manifest(self) -> SourceManifest:
        return self._manifest

    def open(self) -> None:
        if self._opened:
            return
        if self._manifest.credential_ref and self._password is None:
            raise StructuredError(
                ErrorCode.CRED_NOT_FOUND,
                f"env var {self._manifest.credential_ref} not set",
                context={"source_id": self.source_id},
            )
        try:
            self._driver = self._connect_factory(self._cfg, self._password)
        except Exception as e:
            raise StructuredError(
                ErrorCode.CONNECTION_FAILED,
                f"Neo4j connect failed: {e}",
                context={"source_id": self.source_id},
            ) from e
        self._opened = True

    def close(self) -> None:
        if self._driver is not None:
            with contextlib.suppress(Exception):
                self._driver.close()
            self._driver = None
        self._opened = False

    def is_open(self) -> bool:
        return self._opened

    def __enter__(self) -> Neo4jDataSource:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def discover_schema(self) -> SchemaSnapshot:
        self._ensure_open()
        self._labels, self._rel_types = self._introspect()
        labels = [
            LabelSpec(
                name=lab.name,
                property_specs=lab.sample_props,
                sample_nodes=self._sample_label(
                    lab.name, self.DEFAULT_SAMPLE_SIZE,
                ),
            )
            for lab in self._labels
        ]
        rel_specs = [
            RelTypeSpec(name=rt)
            for rt in self._rel_types
        ]
        return SchemaSnapshot(
            source_id=self.source_id,
            discovered_at=datetime.now(UTC),
            tables=[],
            labels=labels,
            rel_types=rel_specs,
        )

    def sample_rows(
        self, table_or_label: str, n: int = 100,
    ) -> list[dict[str, Any]]:
        self._ensure_open()
        return self._sample_label(table_or_label, n)

    def pull_delta(
        self, cursor: CursorState | None,
    ) -> Iterator[CanonicalRecord]:
        self._ensure_open()
        if not self._labels:
            self._labels, self._rel_types = self._introspect()
        max_cursor_value: str | None = None
        cursor_col: str | None = None
        for lab in self._labels:
            col = lab.cursor_property
            cypher = f"MATCH (n:`{lab.name}`)"
            params: dict[str, Any] = {}
            if (
                cursor is not None
                and col is not None
                and col == cursor.cursor_column
            ):
                cypher += f" WHERE n.`{col}` > $cursor"
                params = {"cursor": cursor.cursor_value}
            if col is not None:
                cypher += f" RETURN n ORDER BY n.`{col}`"
            else:
                cypher += " RETURN n"
            for record in self._run_cypher(cypher, params):
                node = record["n"]
                payload = _node_to_dict(node)
                pk_value = (
                    str(payload.get("id"))
                    if "id" in payload
                    else str(payload.get("uuid", _hash_dict(payload)))
                )
                yield CanonicalRecord(
                    table_or_label=lab.name,
                    payload=payload,
                    primary_key=pk_value,
                    content_hash=_hash_dict(payload),
                )
                if col and col in payload and payload[col] is not None:
                    val = str(payload[col])
                    if max_cursor_value is None or val > max_cursor_value:
                        max_cursor_value = val
                        cursor_col = col
        if cursor_col and max_cursor_value:
            self._last_seen_cursor = CursorState(
                cursor_table=None,
                cursor_column=cursor_col,
                cursor_value=max_cursor_value,
            )

    def advance_cursor(self) -> CursorState | None:
        if self._last_seen_cursor is not None:
            return self._last_seen_cursor
        return CursorState(
            cursor_table=None,
            cursor_column="ingested_at",
            cursor_value=utc_now().isoformat(),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_open(self) -> None:
        if not self._opened or self._driver is None:
            self.open()

    def _introspect(
        self,
    ) -> tuple[list[_DiscoveredLabel], list[str]]:
        labels_raw = [r["label"] for r in self._run_cypher(
            "CALL db.labels() YIELD label RETURN label", {},
        )]
        rel_types = [r["relationshipType"] for r in self._run_cypher(
            "CALL db.relationshipTypes() YIELD relationshipType "
            "RETURN relationshipType", {},
        )]
        labels: list[_DiscoveredLabel] = []
        for name in labels_raw:
            sample = self._sample_label(str(name), 1)
            props: list[ColumnSpec] = []
            cursor_col: str | None = None
            if sample:
                for k in sample[0]:
                    props.append(ColumnSpec(
                        name=str(k),
                        type=type(sample[0][k]).__name__,
                        nullable=True,
                        sample_values=[],
                    ))
                cursor_col = _pick_cursor_property(list(sample[0].keys()))
            labels.append(_DiscoveredLabel(
                name=str(name), sample_props=props,
                cursor_property=cursor_col,
            ))
        return labels, [str(r) for r in rel_types]

    def _sample_label(self, label: str, n: int) -> list[dict[str, Any]]:
        cypher = f"MATCH (n:`{label}`) RETURN n LIMIT $n"
        try:
            return [
                _node_to_dict(r["n"])
                for r in self._run_cypher(cypher, {"n": int(n)})
            ]
        except Exception:
            return []

    def _run_cypher(
        self, cypher: str, params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        assert self._driver is not None
        with self._driver.session(database=self._cfg.database) as session:
            result = session.run(cypher, **params)
            return [record.data() for record in result]


def _pick_cursor_property(props: list[str]) -> str | None:
    for cand in ("updated_at", "modified", "created_at", "ts"):
        if cand in props:
            return cand
    return None


def _node_to_dict(node: Any) -> dict[str, Any]:
    # neo4j Node has .items() OR is already a dict (when going through
    # `record.data()`); cover both.
    if isinstance(node, dict):
        return {str(k): v for k, v in node.items()}
    if hasattr(node, "items"):
        return {str(k): v for k, v in node.items()}
    return {"value": str(node)}


def _default_neo4j_factory(
    cfg: Neo4jConfig, password: str | None,
) -> _Neo4jDriverProto:
    from neo4j import GraphDatabase  # noqa: PLC0415

    auth = (cfg.user, password or "")
    return cast(_Neo4jDriverProto, GraphDatabase.driver(cfg.uri, auth=auth))


def _hash_dict(d: dict[str, Any]) -> str:
    serialized = repr(sorted((str(k), v) for k, v in d.items())).encode("utf-8")
    return sha256(serialized).hexdigest()[:16]


__all__ = ["Neo4jDataSource"]
