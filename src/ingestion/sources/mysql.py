"""`MySQLDataSource` — V1.5a Phase 2b engine for MySQL / MariaDB.

Uses `mysql-connector-python`. Schema discovery via `INFORMATION_SCHEMA.TABLES`
+ `INFORMATION_SCHEMA.COLUMNS` + `KEY_COLUMN_USAGE`. Mirrors the Postgres
engine surface (FR-1.5a-2.2).
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
    MySQLConfig,
    SchemaSnapshot,
    SourceManifest,
    SourceTier,
    TableSpec,
)
from src.shared.errors import ErrorCode, StructuredError
from src.shared.timestamps import utc_now

_CURSOR_CANDIDATE_COLUMNS: tuple[str, ...] = (
    "updated_at", "modified_at", "created_at", "ingested_utc", "ts",
)


class _MyConnectionProto(Protocol):
    def cursor(self, dictionary: bool = False) -> Any: ...
    def close(self) -> None: ...


ConnectFactory = Callable[[dict[str, Any]], _MyConnectionProto]


@dataclass
class _DiscoveredMyTable:
    schema: str
    name: str
    columns: list[ColumnSpec]
    pk: list[str] | None
    fks: list[ForeignKeySpec]
    cursor_column: str | None


class MySQLDataSource:
    """V1.5a MySQL engine."""

    DEFAULT_SAMPLE_SIZE: int = 100

    def __init__(
        self,
        manifest: SourceManifest,
        *,
        connect_factory: ConnectFactory | None = None,
        password: str | None = None,
    ) -> None:
        if not isinstance(manifest.config, MySQLConfig):
            raise StructuredError(
                ErrorCode.INGESTION_MANIFEST_INVALID,
                "MySQLDataSource requires manifest.config = MySQLConfig",
                context={"engine": manifest.engine},
            )
        self._manifest = manifest
        self._cfg: MySQLConfig = manifest.config
        self._opened = False
        self._conn: _MyConnectionProto | None = None
        self._connect_factory = connect_factory or _default_mysql_factory
        self._discovered: list[_DiscoveredMyTable] = []
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
        cfg = {
            "host": self._cfg.host,
            "port": self._cfg.port,
            "database": self._cfg.database,
            "user": self._cfg.user,
        }
        if self._password:
            cfg["password"] = self._password
        if self._cfg.ssl_disabled:
            cfg["ssl_disabled"] = True
        try:
            self._conn = self._connect_factory(cfg)
        except Exception as e:
            raise StructuredError(
                ErrorCode.CONNECTION_FAILED,
                f"MySQL connect failed: {e}",
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

    def __enter__(self) -> MySQLDataSource:
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
                name=t.name,
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
            tables=tables, labels=[], rel_types=[],
        )

    def sample_rows(
        self, table_or_label: str, n: int = 100,
    ) -> list[dict[str, Any]]:
        self._ensure_open()
        return self._sample(self._cfg.database, table_or_label, n)

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
            qualified = f'`{table.schema}`.`{table.name}`'
            sql = f"SELECT * FROM {qualified}"
            args: tuple[Any, ...] = ()
            if (
                cursor is not None
                and cursor_col is not None
                and cursor_col == cursor.cursor_column
            ):
                sql += f" WHERE `{cursor_col}` > %s"
                args = (cursor.cursor_value,)
            if cursor_col is not None:
                sql += f" ORDER BY `{cursor_col}`"
            cur = conn.cursor(dictionary=True)
            cur.execute(sql, args)
            for row in cur.fetchall():
                row_dict = dict(row)
                pk_value = (
                    str(row_dict.get(table.pk[0]))
                    if table.pk and table.pk[0] in row_dict
                    else "|".join(str(v) for v in row_dict.values())[:64]
                )
                yield CanonicalRecord(
                    table_or_label=table.name,
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

    def _ensure_open(self) -> None:
        if not self._opened or self._conn is None:
            self.open()

    def _connection(self) -> _MyConnectionProto:
        assert self._conn is not None, "open() must be called first"
        return self._conn

    def _introspect(self) -> list[_DiscoveredMyTable]:
        conn = self._connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE' "
            "ORDER BY TABLE_NAME",
            (self._cfg.database,),
        )
        rows = cur.fetchall()
        out: list[_DiscoveredMyTable] = []
        for row in rows:
            schema = str(row["TABLE_SCHEMA"])
            name = str(row["TABLE_NAME"])
            cols = self._columns(schema, name)
            pk = self._primary_key(schema, name)
            fks = self._foreign_keys(schema, name)
            cursor_col = self._pick_cursor_column(cols)
            out.append(_DiscoveredMyTable(
                schema=schema, name=name,
                columns=cols, pk=pk, fks=fks, cursor_column=cursor_col,
            ))
        return out

    def _columns(self, schema: str, table: str) -> list[ColumnSpec]:
        cur = self._connection().cursor(dictionary=True)
        cur.execute(
            "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE "
            "FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
            "ORDER BY ORDINAL_POSITION",
            (schema, table),
        )
        return [
            ColumnSpec(
                name=str(r["COLUMN_NAME"]),
                type=str(r["DATA_TYPE"]),
                nullable=str(r["IS_NULLABLE"]).upper() == "YES",
                sample_values=[],
            )
            for r in cur.fetchall()
        ]

    def _primary_key(self, schema: str, table: str) -> list[str] | None:
        cur = self._connection().cursor(dictionary=True)
        cur.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
            "  AND CONSTRAINT_NAME = 'PRIMARY' "
            "ORDER BY ORDINAL_POSITION",
            (schema, table),
        )
        rows = [str(r["COLUMN_NAME"]) for r in cur.fetchall()]
        return rows or None

    def _foreign_keys(self, schema: str, table: str) -> list[ForeignKeySpec]:
        cur = self._connection().cursor(dictionary=True)
        cur.execute(
            "SELECT CONSTRAINT_NAME, COLUMN_NAME, "
            "  REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME "
            "FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
            "  AND REFERENCED_TABLE_NAME IS NOT NULL "
            "ORDER BY CONSTRAINT_NAME, ORDINAL_POSITION",
            (schema, table),
        )
        by_constraint: dict[str, list[tuple[str, str, str]]] = {}
        for r in cur.fetchall():
            by_constraint.setdefault(
                str(r["CONSTRAINT_NAME"]), [],
            ).append((
                str(r["COLUMN_NAME"]),
                str(r["REFERENCED_TABLE_NAME"]),
                str(r["REFERENCED_COLUMN_NAME"]),
            ))
        out: list[ForeignKeySpec] = []
        for entries in by_constraint.values():
            cols = [e[0] for e in entries]
            ref_table = entries[0][1]
            ref_cols = [e[2] for e in entries]
            out.append(ForeignKeySpec(
                columns=cols, references_table=ref_table,
                references_columns=ref_cols,
            ))
        return out

    def _sample(self, schema: str, table: str, n: int) -> list[dict[str, Any]]:
        cur = self._connection().cursor(dictionary=True)
        try:
            cur.execute(
                f"SELECT * FROM `{schema}`.`{table}` LIMIT %s",
                (max(0, int(n)),),
            )
            return [dict(r) for r in cur.fetchall()]
        except Exception:
            return []

    def _pick_cursor_column(self, columns: list[ColumnSpec]) -> str | None:
        names = {c.name.lower(): c.name for c in columns}
        for candidate in _CURSOR_CANDIDATE_COLUMNS:
            if candidate in names:
                return names[candidate]
        return None


def _default_mysql_factory(cfg: dict[str, Any]) -> _MyConnectionProto:
    import mysql.connector  # noqa: PLC0415

    return cast(_MyConnectionProto, mysql.connector.connect(**cfg))


def _hash_dict(d: dict[str, Any]) -> str:
    return sha256(repr(sorted(d.items())).encode("utf-8")).hexdigest()[:16]


__all__ = ["MySQLDataSource"]
