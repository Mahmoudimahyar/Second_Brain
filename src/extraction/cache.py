from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from src.shared.timestamps import to_iso, utc_now


@dataclass(frozen=True)
class CacheEntry:
    cache_key: str
    output_json: str
    vendor: str
    model: str
    model_version: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    cost_usd: float


class ExtractionCache:
    """Content-addressable extraction cache per FR-2.4 + R-008 §1.8.

    cache_key = sha256(
        thread_content + prompt_id + prompt_version + schema_hash
        + model_id + model_version
    )

    Cache read happens BEFORE any API call; cache write happens BEFORE returning
    a Gateway response. On the second identical sweep we expect cache_hit ≥ 80%
    per NFR-3.
    """

    def __init__(self, sqlite_path: Path) -> None:
        self._sqlite_path = Path(sqlite_path)
        self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS extraction_cache (
                    cache_key            TEXT PRIMARY KEY,
                    output_json          TEXT NOT NULL,
                    vendor               TEXT,
                    model                TEXT,
                    model_version        TEXT,
                    input_tokens         INTEGER,
                    output_tokens        INTEGER,
                    cached_input_tokens  INTEGER,
                    cost_usd             REAL,
                    created_utc          TEXT NOT NULL
                );
                """,
            )

    @staticmethod
    def make_key(
        *,
        thread_content: str,
        prompt_id: str,
        prompt_version: str,
        schema_hash: str,
        model_id: str,
        model_version: str,
        feedback_context_hash: str | None = None,
    ) -> str:
        """Build a content-addressable cache key.

        V1.5b (FR-1.5b-7.5): when `feedback_context_hash` is supplied, it
        becomes part of the key. Pass-4 templates that load a `ContextBlock`
        invalidate their cache automatically when feedback decisions change.
        V1 callers that don't pass it get the original 6-part key shape.
        """

        h = sha256()
        parts: tuple[str, ...] = (
            thread_content, prompt_id, prompt_version,
            schema_hash, model_id, model_version,
        )
        if feedback_context_hash is not None:
            parts = (*parts, feedback_context_hash)
        for part in parts:
            h.update(part.encode("utf-8"))
            h.update(b"|")
        return f"cache:{h.hexdigest()[:32]}"

    def get(self, cache_key: str) -> CacheEntry | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM extraction_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        return CacheEntry(
            cache_key=row["cache_key"],
            output_json=row["output_json"],
            vendor=row["vendor"] or "",
            model=row["model"] or "",
            model_version=row["model_version"] or "",
            input_tokens=int(row["input_tokens"] or 0),
            output_tokens=int(row["output_tokens"] or 0),
            cached_input_tokens=int(row["cached_input_tokens"] or 0),
            cost_usd=float(row["cost_usd"] or 0.0),
        )

    def put(self, entry: CacheEntry) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO extraction_cache "
                "(cache_key, output_json, vendor, model, model_version, "
                " input_tokens, output_tokens, cached_input_tokens, "
                " cost_usd, created_utc) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.cache_key, entry.output_json, entry.vendor,
                    entry.model, entry.model_version,
                    entry.input_tokens, entry.output_tokens,
                    entry.cached_input_tokens, entry.cost_usd,
                    to_iso(utc_now()),
                ),
            )
            conn.commit()

    def put_output(
        self,
        cache_key: str,
        output: Any,
        *,
        vendor: str = "",
        model: str = "",
        model_version: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        self.put(CacheEntry(
            cache_key=cache_key,
            output_json=json.dumps(output) if not isinstance(output, str) else output,
            vendor=vendor, model=model, model_version=model_version,
            input_tokens=input_tokens, output_tokens=output_tokens,
            cached_input_tokens=0,
            cost_usd=cost_usd,
        ))

    def hit_rate(self, attempts: int, hits: int) -> float:
        return hits / attempts if attempts > 0 else 0.0

    def size(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM extraction_cache").fetchone()
        return int(row[0]) if row else 0
