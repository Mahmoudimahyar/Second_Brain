"""`SQLiteDataSource` — V1.5a Phase 2c engine for SQLite files.

Uses stdlib `sqlite3`. Schema discovery via `sqlite_master` + `PRAGMA
table_info` + `PRAGMA foreign_key_list`. Row sampling honours per-table
LIMIT. Cursor selection falls back: `updated_at` → `created_at` → `pk`.

Notably also serves as a self-test fixture (FR-1.5a-2.3): pointing this
engine at V1's own L1 SQLite side-store re-ingests it round-trippably.
"""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from types import TracebackType
from typing import Any

from src.ingestion.sources.base import (
    CanonicalRecord,
    ColumnSpec,
    CursorState,
    ForeignKeySpec,
    SchemaSnapshot,
    SourceManifest,
    SourceTier,
    SQLiteConfig,
    TableSpec,
)
from src.shared.errors import ErrorCode, StructuredError
from src.shared.timestamps import utc_now

# Tables whose name starts with one of these prefixes are skipped during
# discovery (SQLite internal tables + common operational shapes).
_SQLITE_INTERNAL_PREFIXES: tuple[str, ...] = (
    "sqlite_",
)


# Candidate cursor columns in priority order.
_CURSOR_CANDIDATE_COLUMNS: tuple[str, ...] = (
    "updated_at",
    "modified_at",
    "created_at",
    "ingested_utc",
)


@dataclass
class _DiscoveredTable:
    name: str
    columns: list[ColumnSpec]
    pk: list[str] | None
    fks: list[ForeignKeySpec]
    cursor_column: str | None


class SQLiteDataSource:
    """V1.5a SQLite engine. Implements the `DataSource` Protocol."""

    DEFAULT_SAMPLE_SIZE: int = 100

    def __init__(self, manifest: SourceManifest) -> None:
        if not isinstance(manifest.config, SQLiteConfig):
            raise StructuredError(
                ErrorCode.INGESTION_MANIFEST_INVALID,
                "SQLiteDataSource requires manifest.config = SQLiteConfig",
                context={"engine": manifest.engine},
            )
        self._manifest = manifest
        self._cfg: SQLiteConfig = manifest.config
        self._file_path = Path(self._cfg.file_path)
        self._opened = False
        self._conn: sqlite3.Connection | None = None
        self._discovered: list[_DiscoveredTable] = []
        self._last_seen_cursor: CursorState | None = None

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
        if not self._file_path.is_file():
            raise StructuredError(
                ErrorCode.CONNECTION_FAILED,
                f"SQLite file not found: {self._file_path}",
                context={
                    "source_id": self.source_id,
                    "file_path": str(self._file_path),
                },
            )
        try:
            self._conn = sqlite3.connect(self._file_path)
            self._conn.row_factory = sqlite3.Row
        except sqlite3.Error as e:
            raise StructuredError(
                ErrorCode.CONNECTION_FAILED,
                f"SQLite open failed: {e}",
                context={"source_id": self.source_id},
            ) from e
        self._opened = True

    def close(self) -> None:
        if self._conn is not None:
            with contextlib.suppress(sqlite3.Error):
                self._conn.close()
            self._conn = None
        self._opened = False

    def is_open(self) -> bool:
        return self._opened

    def __enter__(self) -> SQLiteDataSource:
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
                sample_rows=self._sample(t.name, self.DEFAULT_SAMPLE_SIZE),
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
        return self._sample(table_or_label, n)

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
            sql = f'SELECT * FROM "{table.name}"'
            args: list[Any] = []
            if cursor is not None and cursor_col == cursor.cursor_column:
                # Honor incremental cursor only when the column matches.
                sql += f' WHERE "{cursor_col}" > ?'
                args.append(cursor.cursor_value)
            if cursor_col is not None:
                sql += f' ORDER BY "{cursor_col}"'
            rows = conn.execute(sql, args).fetchall()
            for row in rows:
                row_dict = dict(row)
                pk_value = (
                    str(row_dict.get(table.pk[0]))
                    if table.pk and table.pk[0] in row_dict
                    else "|".join(
                        str(v) for v in row_dict.values()
                    )[:64]
                )
                yield CanonicalRecord(
                    table_or_label=table.name,
                    payload=row_dict,
                    primary_key=pk_value,
                    content_hash=_hash_dict(row_dict),
                )
                if cursor_col and cursor_col in row_dict and row_dict[cursor_col] is not None:
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
        # No pull seen yet — derive a cursor by inspecting the highest
        # cursor-candidate value across all tables.
        self._ensure_open()
        if not self._discovered:
            self._discovered = self._introspect()
        conn = self._connection()
        best_value: str | None = None
        best_column: str | None = None
        for table in self._discovered:
            col = table.cursor_column or (table.pk[0] if table.pk else None)
            if col is None:
                continue
            try:
                row = conn.execute(
                    f'SELECT MAX("{col}") FROM "{table.name}"',
                ).fetchone()
            except sqlite3.Error:
                continue
            if row is None or row[0] is None:
                continue
            val = str(row[0])
            if best_value is None or val > best_value:
                best_value = val
                best_column = col
        if best_column and best_value:
            return CursorState(
                cursor_table=None,
                cursor_column=best_column,
                cursor_value=best_value,
            )
        # Fallback to a wall-clock cursor.
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

    def _connection(self) -> sqlite3.Connection:
        assert self._conn is not None, "open() must be called first"
        return self._conn

    def _introspect(self) -> list[_DiscoveredTable]:
        conn = self._connection()
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' "
            "ORDER BY name",
        ).fetchall()
        discovered: list[_DiscoveredTable] = []
        for row in rows:
            name = str(row["name"])
            if name.startswith(_SQLITE_INTERNAL_PREFIXES):
                continue
            columns, pk = self._columns_and_pk(name)
            fks = self._foreign_keys(name)
            cursor_col = self._pick_cursor_column(columns)
            discovered.append(_DiscoveredTable(
                name=name, columns=columns, pk=pk, fks=fks,
                cursor_column=cursor_col,
            ))
        return discovered

    def _columns_and_pk(
        self, table: str,
    ) -> tuple[list[ColumnSpec], list[str] | None]:
        conn = self._connection()
        info_rows = conn.execute(
            f'PRAGMA table_info("{table}")',
        ).fetchall()
        columns: list[ColumnSpec] = []
        pk_pairs: list[tuple[int, str]] = []
        for r in info_rows:
            columns.append(ColumnSpec(
                name=str(r["name"]),
                type=str(r["type"] or ""),
                nullable=not bool(r["notnull"]),
                sample_values=[],
            ))
            if int(r["pk"]) > 0:
                pk_pairs.append((int(r["pk"]), str(r["name"])))
        pk_pairs.sort()
        pk = [n for _, n in pk_pairs] or None
        return columns, pk

    def _foreign_keys(self, table: str) -> list[ForeignKeySpec]:
        conn = self._connection()
        rows = conn.execute(
            f'PRAGMA foreign_key_list("{table}")',
        ).fetchall()
        # Each row: id, seq, table, from, to, on_update, on_delete, match
        by_id: dict[int, list[Any]] = {}
        for r in rows:
            by_id.setdefault(int(r["id"]), []).append(r)
        fks: list[ForeignKeySpec] = []
        for entries in by_id.values():
            entries.sort(key=lambda e: int(e["seq"]))
            fks.append(ForeignKeySpec(
                columns=[str(e["from"]) for e in entries],
                references_table=str(entries[0]["table"]),
                references_columns=[str(e["to"]) for e in entries],
            ))
        return fks

    def _sample(self, table: str, n: int) -> list[dict[str, Any]]:
        conn = self._connection()
        try:
            rows = conn.execute(
                f'SELECT * FROM "{table}" LIMIT ?', (max(0, int(n)),),
            ).fetchall()
        except sqlite3.Error:
            return []
        return [dict(r) for r in rows]

    def _pick_cursor_column(self, columns: list[ColumnSpec]) -> str | None:
        names = {c.name.lower(): c.name for c in columns}
        for candidate in _CURSOR_CANDIDATE_COLUMNS:
            if candidate in names:
                return names[candidate]
        return None


def _hash_dict(d: dict[str, Any]) -> str:
    serialized = repr(sorted(d.items())).encode("utf-8")
    return sha256(serialized).hexdigest()[:16]


__all__ = ["SQLiteDataSource"]
