from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.shared.content_hash import content_hash_file
from src.shared.errors import ErrorCode, StructuredError
from src.shared.ids import make_dump_id
from src.shared.timestamps import from_iso, to_iso, utc_now

if TYPE_CHECKING:
    from src.ingestion.sources.base import DataSource, SourceManifest

SourceTier = Literal["L1", "L2", "L3", "L4", "L5"]
Rank = Literal["preferred", "normal", "deprecated"]


class DumpManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str
    source_tier: SourceTier
    rank_default: Rank
    license: str
    t_valid_range: tuple[datetime, datetime]
    source_url: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    schema_hint: dict[str, Any] | None = None

    @field_validator("source_name")
    @classmethod
    def _source_name_non_empty(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("source_name must be non-empty")
        return cleaned


class DumpReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dump_id: str
    source_tier: SourceTier
    content_hashes: list[str]
    t_ingest_from: datetime
    validation_result: str
    duplicate_of: str | None = None


class IngestionService:
    """V1 ingestion plane entry point. Implements FR-1.1.

    Copies payload files to an immutable per-dump directory under
    `dumps_root/<source_tier>/<ingest_date>/<dump_id>/`, records the dump in
    the SQLite side store, and emits a `DumpReceipt`.

    Idempotency (NFR-5): identical content hashes return the prior receipt
    with `duplicate_of` set, without re-copying payload files.
    """

    def __init__(self, dumps_root: Path, sqlite_path: Path) -> None:
        self._dumps_root = Path(dumps_root)
        self._sqlite_path = Path(sqlite_path)
        self._dumps_root.mkdir(parents=True, exist_ok=True)
        self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def register_data_source(
        self,
        manifest: SourceManifest,
        *,
        actor: str = "system",
        confirm_l1_immutable: bool = False,
    ) -> DataSource:
        """V1.5a entry point — construct a `DataSource` from a manifest.

        Per FR-1.5a-1.2: for `engine='local_file'` this returns a
        `LocalFileDataSource` wrapping the chosen V1 adapter. For DB engines
        (V1.5a Phase 2+) this returns the engine-specific `DataSource`.

        Persists the manifest into the `DataSourceRegistry` (FR-1.5a-4 +
        FR-1.5a-8) before returning. L1 tier requires
        `confirm_l1_immutable=True` per ADR-014.

        V1's `register_dump()` remains unchanged for back-compat.
        """

        from src.ingestion.sources.base import (  # noqa: PLC0415
            LocalFileConfig,
            MySQLConfig,
            Neo4jConfig,
            PostgresConfig,
            SQLiteConfig,
        )
        from src.ingestion.sources.local_file import (  # noqa: PLC0415
            LocalFileDataSource,
        )
        from src.ingestion.sources.mysql import MySQLDataSource  # noqa: PLC0415
        from src.ingestion.sources.neo4j import Neo4jDataSource  # noqa: PLC0415
        from src.ingestion.sources.postgres import (  # noqa: PLC0415
            PostgresDataSource,
        )
        from src.ingestion.sources.registry import (  # noqa: PLC0415
            DataSourceRegistry,
        )
        from src.ingestion.sources.sqlite import SQLiteDataSource  # noqa: PLC0415

        registry = DataSourceRegistry(sqlite_path=self._sqlite_path)
        registry.register(
            manifest,
            actor=actor,
            confirm_l1_immutable=confirm_l1_immutable,
        )

        if isinstance(manifest.config, LocalFileConfig):
            return LocalFileDataSource(manifest)
        if isinstance(manifest.config, PostgresConfig):
            return PostgresDataSource(manifest)
        if isinstance(manifest.config, MySQLConfig):
            return MySQLDataSource(manifest)
        if isinstance(manifest.config, SQLiteConfig):
            return SQLiteDataSource(manifest)
        if isinstance(manifest.config, Neo4jConfig):
            return Neo4jDataSource(manifest)
        raise StructuredError(
            ErrorCode.ENGINE_UNSUPPORTED,
            f"register_data_source: engine {manifest.engine!r} not supported",
            context={"engine": manifest.engine},
        )

    def register_dump(
        self,
        source_tier: SourceTier,
        manifest: DumpManifest,
        payload_paths: list[Path],
    ) -> DumpReceipt:
        self._validate(source_tier, manifest, payload_paths)

        content_hashes = [content_hash_file(Path(p)) for p in payload_paths]
        dump_id = make_dump_id(source_tier, content_hashes)

        existing = self._find_dump(dump_id)
        if existing is not None:
            return DumpReceipt(
                dump_id=existing["dump_id"],
                source_tier=existing["source_tier"],
                content_hashes=json.loads(existing["content_hashes_json"]),
                t_ingest_from=from_iso(existing["t_ingest_from"]),
                validation_result="ok",
                duplicate_of=existing["dump_id"],
            )

        ingest_dt = utc_now()
        payload_dir = self._materialize_payload_dir(source_tier, ingest_dt, dump_id)
        for src in payload_paths:
            shutil.copy2(src, payload_dir / Path(src).name)

        self._insert_dump(
            dump_id=dump_id,
            source_tier=source_tier,
            manifest=manifest,
            content_hashes=content_hashes,
            payload_dir=payload_dir,
            ingest_dt=ingest_dt,
        )

        return DumpReceipt(
            dump_id=dump_id,
            source_tier=source_tier,
            content_hashes=content_hashes,
            t_ingest_from=ingest_dt,
            validation_result="ok",
            duplicate_of=None,
        )

    @staticmethod
    def _validate(
        source_tier: SourceTier,
        manifest: DumpManifest,
        payload_paths: list[Path],
    ) -> None:
        if source_tier != manifest.source_tier:
            raise StructuredError(
                ErrorCode.INGESTION_MANIFEST_INVALID,
                f"source_tier mismatch: arg={source_tier} manifest={manifest.source_tier}",
                context={"arg": source_tier, "manifest": manifest.source_tier},
            )
        if not payload_paths:
            raise StructuredError(
                ErrorCode.INGESTION_PAYLOAD_MISSING,
                "register_dump requires at least one payload file",
            )
        missing = [str(p) for p in payload_paths if not Path(p).is_file()]
        if missing:
            raise StructuredError(
                ErrorCode.INGESTION_PAYLOAD_MISSING,
                f"payload files not found: {missing}",
                context={"missing": missing},
            )

    def _materialize_payload_dir(
        self, source_tier: SourceTier, ingest_dt: datetime, dump_id: str,
    ) -> Path:
        date_dir = ingest_dt.strftime("%Y-%m-%d")
        slug = dump_id.split(":", 1)[1]
        payload_dir = self._dumps_root / source_tier / date_dir / slug
        payload_dir.mkdir(parents=True, exist_ok=True)
        return payload_dir

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS dump (
                    dump_id              TEXT PRIMARY KEY,
                    source_tier          TEXT NOT NULL,
                    source_name          TEXT NOT NULL,
                    manifest_json        TEXT NOT NULL,
                    content_hashes_json  TEXT NOT NULL,
                    payload_dir          TEXT NOT NULL,
                    t_ingest_from        TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_dump_source_tier ON dump(source_tier);
                """,
            )

    def _find_dump(self, dump_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            row: sqlite3.Row | None = conn.execute(
                "SELECT * FROM dump WHERE dump_id = ?", (dump_id,),
            ).fetchone()
            return row

    def _insert_dump(
        self,
        *,
        dump_id: str,
        source_tier: SourceTier,
        manifest: DumpManifest,
        content_hashes: list[str],
        payload_dir: Path,
        ingest_dt: datetime,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO dump (dump_id, source_tier, source_name, manifest_json, "
                "content_hashes_json, payload_dir, t_ingest_from) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    dump_id,
                    source_tier,
                    manifest.source_name,
                    manifest.model_dump_json(),
                    json.dumps(content_hashes),
                    str(payload_dir),
                    to_iso(ingest_dt),
                ),
            )
            conn.commit()
