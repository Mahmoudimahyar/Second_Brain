"""`PostgresDataSource` — V1.5a Phase 2a engine for PostgreSQL.

Uses `psycopg[binary]` 3.x + `psycopg_pool`. Schema discovery via
`information_schema.tables` + `information_schema.columns` + foreign-key
introspection. Row sampling via `LIMIT`. Cursor selection: `updated_at` →
`created_at` → primary-key column (FR-1.5a-6.1).

Credentials come from `.env` via `credential_ref` (env-var name); never
appear in `audit_log`, `structlog`, or `langfuse` events (FR-1.5a-2.5 +
NFR-1.5a-7).

For unit tests + offline dev, the connect path is mockable via the
`connect_factory` constructor argument. Real-DB integration tests live in
`tests/ingestion/sources/test_postgres_integration.py` and require Docker
(testcontainers) — skipped automatically when Docker is unavailable.
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
    ForeignKeySpec,
    PostgresConfig,
    SchemaSnapshot,
    SourceManifest,
    SourceTier,
    TableSpec,
)
from src.shared.errors import ErrorCode, StructuredError
from src.shared.timestamps import utc_now

_CURSOR_CANDIDATE_COLUMNS: tuple[str, ...] = (
    "updated_at",
    "modified_at",
    "created_at",
    "ingested_utc",
    "ts",
)


class _PgConnectionProto(Protocol):
    """Minimum interface the engine needs — for test-mock injectability."""

    def execute(self, sql: str, args: tuple[Any, ...] = ()) -> Any: ...
    def cursor(self) -> Any: ...
    def close(self) -> None: ...


ConnectFactory = Callable[[str], _PgConnectionProto]


@dataclass
class _DiscoveredPgTable:
    schema: str
    name: str
    columns: list[ColumnSpec]
    pk: list[str] | None
    fks: list[ForeignKeySpec]
    cursor_column: str | None


class PostgresDataSource:
    """V1.5a Postgres engine. Implements the `DataSource` Protocol."""

    DEFAULT_SAMPLE_SIZE: int = 100

    def __init__(
        self,
        manifest: SourceManifest,
        *,
        connect_factory: ConnectFactory | None = None,
        password: str | None = None,
    ) -> None:
        if not isinstance(manifest.config, PostgresConfig):
            raise StructuredError(
                ErrorCode.INGESTION_MANIFEST_INVALID,
                "PostgresDataSource requires manifest.config = PostgresConfig",
                context={"engine": manifest.engine},
            )
        self._manifest = manifest
        self._cfg: PostgresConfig = manifest.config
        self._opened = False
        self._conn: _PgConnectionProto | None = None
        self._connect_factory = connect_factory or _default_psycopg_factory
        self._discovered: list[_DiscoveredPgTable] = []
        self._last_seen_cursor: CursorState | None = None
        self._password: str | None = password
        if password is None and manifest.credential_ref:
            self._password = os.environ.get(manifest.credential_ref)

    # ------------------------------------------------------------------
    # Protocol surface
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
        dsn = self._build_dsn()
        try:
            self._conn = self._connect_factory(dsn)
        except Exception as e:
            raise StructuredError(
                ErrorCode.CONNECTION_FAILED,
                f"Postgres connect failed: {e}",
                context={"source_id": self.source_id},
            ) from e
        self._opened = True

    def close(self) -> None:
        if self._conn is not None:
            with contextlib.suppress(Exception):
                self._conn.close()
            self._conn = None
        self._opened = False

    def is_open(self) -> bool:
        return self._opened

    def __enter__(self) -> PostgresDataSource:
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
        self._discovered = self._introspect()
        tables = [
            TableSpec(
                name=_qualify(t.schema, t.name),
                column_specs=t.columns,
                primary_key=t.pk,
                foreign_keys=t.fks,
                sample_rows=self._sample(t.schema, t.name, self.DEFAULT_SAMPLE_SIZE),
            )
            for t in self._discovered
        ]
        return SchemaSnapshot(
            source_id=self.source_id,
            discovered_at=datetime.now(UTC),
            tables=tables,
            labels=[],
            rel_types=[],
        )

    def sample_rows(
        self, table_or_label: str, n: int = 100,
    ) -> list[dict[str, Any]]:
        self._ensure_open()
        if "." in table_or_label:
            schema, name = table_or_label.split(".", 1)
        else:
            schema, name = "public", table_or_label
        return self._sample(schema, name, n)

    def pull_delta(
        self, cursor: CursorState | None,
    ) -> Iterator[CanonicalRecord]:
        self._ensure_open()
        if not self._discovered:
            self._discovered = self._introspect()
        conn = self._connection()
        max_cursor_value: str | None = None
        cursor_column_used: str | None = None
        for table in self._discovered:
            cursor_col = table.cursor_column or (
                table.pk[0] if table.pk else None
            )
            qualified = f'"{table.schema}"."{table.name}"'
            sql = f"SELECT * FROM {qualified}"
            args: tuple[Any, ...] = ()
            if (
                cursor is not None
                and cursor_col is not None
                and cursor_col == cursor.cursor_column
            ):
                sql += f' WHERE "{cursor_col}" > %s'
                args = (cursor.cursor_value,)
            if cursor_col is not None:
                sql += f' ORDER BY "{cursor_col}"'
            cur = conn.cursor()
            cur.execute(sql, args)
            colnames = [d[0] for d in cur.description]
            for row in cur.fetchall():
                row_dict = dict(zip(colnames, row, strict=True))
                pk_value = (
                    str(row_dict.get(table.pk[0]))
                    if table.pk and table.pk[0] in row_dict
                    else "|".join(str(v) for v in row_dict.values())[:64]
                )
                yield CanonicalRecord(
                    table_or_label=_qualify(table.schema, table.name),
                    payload=row_dict,
                    primary_key=pk_value,
                    content_hash=_hash_dict(row_dict),
                )
                if (
                    cursor_col
                    and cursor_col in row_dict
                    and row_dict[cursor_col] is not None
                ):
                    val = str(row_dict[cursor_col])
                    if max_cursor_value is None or val > max_cursor_value:
                        max_cursor_value = val
                        cursor_column_used = cursor_col
        if cursor_column_used and max_cursor_value:
            self._last_seen_cursor = CursorState(
                cursor_table=None,
                cursor_column=cursor_column_used,
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

    def _build_dsn(self) -> str:
        parts = [
            f"host={self._cfg.host}",
            f"port={self._cfg.port}",
            f"dbname={self._cfg.database}",
            f"user={self._cfg.user}",
        ]
        if self._password:
            parts.append(f"password={self._password}")
        parts.append(f"sslmode={self._cfg.ssl_mode}")
        return " ".join(parts)

    def _ensure_open(self) -> None:
        if not self._opened or self._conn is None:
            self.open()

    def _connection(self) -> _PgConnectionProto:
        assert self._conn is not None, "open() must be called first"
        return self._conn

    def _allowed_schemas(self) -> list[str]:
        if self._cfg.schema_filter:
            return list(self._cfg.schema_filter)
        return ["public"]

    def _introspect(self) -> list[_DiscoveredPgTable]:
        conn = self._connection()
        schemas = self._allowed_schemas()
        cur = conn.cursor()
        # ANSI-compatible information_schema query.
        placeholders = ",".join(["%s"] * len(schemas))
        cur.execute(
            f"SELECT table_schema, table_name FROM information_schema.tables "
            f"WHERE table_type = 'BASE TABLE' AND table_schema IN ({placeholders}) "
            f"ORDER BY table_schema, table_name",
            tuple(schemas),
        )
        out: list[_DiscoveredPgTable] = []
        for schema, name in cur.fetchall():
            cols = self._columns(schema, name)
            pk = self._primary_key(schema, name)
            fks = self._foreign_keys(schema, name)
            cursor_col = self._pick_cursor_column(cols)
            out.append(_DiscoveredPgTable(
                schema=str(schema), name=str(name),
                columns=cols, pk=pk, fks=fks, cursor_column=cursor_col,
            ))
        return out

    def _columns(self, schema: str, table: str) -> list[ColumnSpec]:
        conn = self._connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s "
            "ORDER BY ordinal_position",
            (schema, table),
        )
        return [
            ColumnSpec(
                name=str(r[0]),
                type=str(r[1]),
                nullable=str(r[2]).upper() == "YES",
                sample_values=[],
            )
            for r in cur.fetchall()
        ]

    def _primary_key(self, schema: str, table: str) -> list[str] | None:
        conn = self._connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT kcu.column_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name "
            "  AND tc.table_schema = kcu.table_schema "
            "WHERE tc.constraint_type = 'PRIMARY KEY' "
            "  AND tc.table_schema = %s AND tc.table_name = %s "
            "ORDER BY kcu.ordinal_position",
            (schema, table),
        )
        rows = [str(r[0]) for r in cur.fetchall()]
        return rows or None

    def _foreign_keys(
        self, schema: str, table: str,
    ) -> list[ForeignKeySpec]:
        conn = self._connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT tc.constraint_name, kcu.column_name, "
            "  ccu.table_name AS ref_table, ccu.column_name AS ref_column "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name "
            "JOIN information_schema.constraint_column_usage ccu "
            "  ON ccu.constraint_name = tc.constraint_name "
            "WHERE tc.constraint_type = 'FOREIGN KEY' "
            "  AND tc.table_schema = %s AND tc.table_name = %s "
            "ORDER BY tc.constraint_name, kcu.ordinal_position",
            (schema, table),
        )
        by_constraint: dict[str, list[tuple[str, str, str]]] = {}
        for cname, col, ref_table, ref_col in cur.fetchall():
            by_constraint.setdefault(str(cname), []).append(
                (str(col), str(ref_table), str(ref_col)),
            )
        out: list[ForeignKeySpec] = []
        for entries in by_constraint.values():
            cols = [e[0] for e in entries]
            ref_table = entries[0][1]
            ref_cols = [e[2] for e in entries]
            out.append(ForeignKeySpec(
                columns=cols,
                references_table=ref_table,
                references_columns=ref_cols,
            ))
        return out

    def _sample(self, schema: str, table: str, n: int) -> list[dict[str, Any]]:
        conn = self._connection()
        cur = conn.cursor()
        try:
            cur.execute(
                f'SELECT * FROM "{schema}"."{table}" LIMIT %s',
                (max(0, int(n)),),
            )
            colnames = [d[0] for d in cur.description]
            return [
                dict(zip(colnames, row, strict=True))
                for row in cur.fetchall()
            ]
        except Exception:
            return []

    def _pick_cursor_column(self, columns: list[ColumnSpec]) -> str | None:
        names = {c.name.lower(): c.name for c in columns}
        for candidate in _CURSOR_CANDIDATE_COLUMNS:
            if candidate in names:
                return names[candidate]
        return None


def _qualify(schema: str, name: str) -> str:
    return f"{schema}.{name}" if schema and schema != "public" else name


def _hash_dict(d: dict[str, Any]) -> str:
    serialized = repr(sorted(d.items())).encode("utf-8")
    return sha256(serialized).hexdigest()[:16]


def _default_psycopg_factory(dsn: str) -> _PgConnectionProto:
    """Default connection factory using `psycopg` 3.x.

    Lazily imported so the engine module loads without the dep installed
    (Phase 1 + tests outside Postgres scope).
    """

    import psycopg  # noqa: PLC0415

    return cast(_PgConnectionProto, psycopg.connect(dsn))


__all__ = ["PostgresDataSource"]
