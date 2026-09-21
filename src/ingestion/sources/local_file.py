"""`LocalFileDataSource` — wraps V1's file-based adapters as a `DataSource`.

Per FR-1.5a-1.2: each of L1 Excel / L1 PDF / L2 HTML / L5 Reddit / L5 SDN can
be wrapped without behaviour change. The wrapper exposes the V1.5a Protocol
(open/close/discover_schema/sample_rows/pull_delta/manifest/advance_cursor)
while delegating actual parsing to the underlying adapter's `parse()` call.

The "schema" for a file source is the canonical record types the adapter
emits; the "cursor" is the combined content-hash of all payload files
(idempotent on no-change).
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from dataclasses import asdict, fields, is_dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from types import TracebackType
from typing import Any

from src.ingestion.adapters.l1_excel import L1ExcelAdapter, L1IngestResult
from src.ingestion.adapters.l1_pdf import L1PDFAdapter, L1PDFResult
from src.ingestion.adapters.l2_html import L2HtmlAdapter, L2IngestResult
from src.ingestion.adapters.l5_reddit import L5RedditAdapter, L5RedditResult
from src.ingestion.adapters.l5_sdn import L5SDNAdapter, L5SDNResult
from src.ingestion.sources.base import (
    CanonicalRecord,
    ColumnSpec,
    CursorState,
    LocalFileConfig,
    SchemaSnapshot,
    SourceManifest,
    SourceTier,
    TableSpec,
)
from src.shared.content_hash import content_hash_file, content_hash_str
from src.shared.errors import ErrorCode, StructuredError


class LocalFileDataSource:
    """Wraps a V1 file-based `SourceAdapter` as a V1.5a `DataSource`.

    Construction takes a `SourceManifest` whose `config` is a `LocalFileConfig`.
    The adapter kind + payload paths come from that config.

    The wrapper is context-manager safe and idempotent on repeated lifecycle
    cycles (open/close).
    """

    def __init__(self, manifest: SourceManifest) -> None:
        if not isinstance(manifest.config, LocalFileConfig):
            raise StructuredError(
                ErrorCode.INGESTION_MANIFEST_INVALID,
                "LocalFileDataSource requires manifest.config = LocalFileConfig",
                context={"engine": manifest.engine},
            )
        self._manifest = manifest
        self._cfg: LocalFileConfig = manifest.config
        self._paths: list[Path] = [Path(p) for p in self._cfg.paths]
        self._opened: bool = False
        self._last_seen_hash: str | None = None

    # ------------------------------------------------------------------
    # DataSource Protocol surface
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
        missing = [str(p) for p in self._paths if not p.exists()]
        if missing:
            raise StructuredError(
                ErrorCode.INGESTION_PAYLOAD_MISSING,
                f"LocalFileDataSource missing payload(s): {missing}",
                context={"source_id": self.source_id, "missing": missing},
            )
        self._opened = True

    def close(self) -> None:
        self._opened = False

    def is_open(self) -> bool:
        return self._opened

    def __enter__(self) -> LocalFileDataSource:
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
        """Return the canonical-record-type descriptors the wrapped adapter emits.

        For file sources the "schema" is statically known per adapter kind;
        we don't need to crack the file open to enumerate it.
        """

        return SchemaSnapshot(
            source_id=self.source_id,
            discovered_at=datetime.now(UTC),
            tables=_schema_tables_for(self._cfg.adapter),
            labels=[],
            rel_types=[],
            snapshot_hash=None,
        )

    def sample_rows(
        self, table_or_label: str, n: int = 100,
    ) -> list[dict[str, Any]]:
        """Return up to `n` sample rows from the named table.

        Implemented in terms of `pull_delta` — for a file source the cost is
        the full parse anyway; the slice happens after. This keeps the
        Protocol's sampling semantics consistent with SQL engines (Phase 2)
        where sampling uses LIMIT.
        """

        out: list[dict[str, Any]] = []
        for rec in self.pull_delta(cursor=None):
            if rec.table_or_label != table_or_label:
                continue
            out.append(_payload_to_dict(rec.payload))
            if len(out) >= n:
                break
        return out

    def pull_delta(
        self, cursor: CursorState | None,
    ) -> Iterator[CanonicalRecord]:
        """Yield canonical records since `cursor`. Idempotent on no-change.

        Cursor semantics for file sources: a fixed-content payload set
        produces the same content_hash every pull. If `cursor.cursor_value`
        matches the current hash, we yield nothing (FR-1.5a-6.2 idempotency).
        Otherwise we re-parse the entire payload — file sources are batch by
        nature; per-record incrementality is not meaningful.
        """

        if not self._opened:
            # Auto-open for caller convenience inside `with` blocks the user
            # may forget; FR-1.5a-1.1 calls for context-manager safety.
            self.open()

        current_hash = self._compute_content_hash()
        self._last_seen_hash = current_hash
        if cursor is not None and cursor.cursor_value == current_hash:
            return  # idempotent no-op

        result = self._invoke_adapter()
        yield from _records_from_result(result)

    def advance_cursor(self) -> CursorState:
        """Cursor = content-hash of all payload files concatenated."""

        return CursorState(
            cursor_table=None,
            cursor_column="content_hash",
            cursor_value=self._last_seen_hash or self._compute_content_hash(),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _compute_content_hash(self) -> str:
        # For directories (SDN posts_dir), hash the listing; for files, the
        # file contents. Combine into a stable single value.
        h = sha256()
        for p in self._paths:
            h.update(b"|")
            h.update(str(p).encode("utf-8"))
            if p.is_file():
                h.update(b":F:")
                h.update(content_hash_file(p).encode("ascii"))
            elif p.is_dir():
                h.update(b":D:")
                for child in sorted(p.iterdir()):
                    h.update(b"/")
                    h.update(child.name.encode("utf-8"))
                    if child.is_file():
                        h.update(b"=")
                        h.update(content_hash_file(child).encode("ascii"))
        return h.hexdigest()

    def _invoke_adapter(self) -> object:
        kind = self._cfg.adapter
        if kind == "l5_reddit":
            posts = self._paths[0]
            comments = self._paths[1] if len(self._paths) > 1 else None
            return L5RedditAdapter().parse(posts, comments)
        if kind == "l5_sdn":
            metadata = self._paths[0]
            posts_dir = self._paths[1]
            return L5SDNAdapter().parse(metadata, posts_dir)
        if kind == "l1_pdf":
            return L1PDFAdapter().parse(self._paths[0])
        if kind == "l2_html":
            return L2HtmlAdapter().parse(self._paths)
        if kind == "l1_excel":
            # L1ExcelAdapter persists to a SQLite side store; for the
            # DataSource wrapping we use a scratch in-memory db when the
            # caller hasn't wired a real path. Real callers use the V1 CLI
            # path; this branch keeps the wrapper unit-testable.
            adapter = L1ExcelAdapter(sqlite_path=Path(":memory:"))
            return adapter.parse(self._paths[0])
        raise StructuredError(
            ErrorCode.INGESTION_MANIFEST_INVALID,
            f"unknown local_file adapter kind: {kind!r}",
            context={"source_id": self.source_id, "adapter": kind},
        )


# ----------------------------------------------------------------------
# Per-adapter schema descriptors (statically known)
# ----------------------------------------------------------------------


def _schema_tables_for(adapter_kind: str) -> list[TableSpec]:
    if adapter_kind == "l5_reddit":
        return [
            TableSpec(
                name="post",
                column_specs=_columns_from_dataclass_module(
                    "src.ingestion.adapters.l5_reddit", "RedditPost",
                ),
                primary_key=["post_id"],
            ),
            TableSpec(
                name="comment",
                column_specs=_columns_from_dataclass_module(
                    "src.ingestion.adapters.l5_reddit", "RedditComment",
                ),
                primary_key=["comment_id"],
            ),
            TableSpec(
                name="user",
                column_specs=_columns_from_dataclass_module(
                    "src.ingestion.adapters.l5_reddit", "RedditUser",
                ),
                primary_key=["user_id"],
            ),
        ]
    if adapter_kind == "l5_sdn":
        return [
            TableSpec(
                name="thread",
                column_specs=_columns_from_dataclass_module(
                    "src.ingestion.adapters.l5_sdn", "SDNThread",
                ),
                primary_key=["thread_id"],
            ),
            TableSpec(
                name="post",
                column_specs=_columns_from_dataclass_module(
                    "src.ingestion.adapters.l5_sdn", "SDNPost",
                ),
                primary_key=["post_id"],
            ),
            TableSpec(
                name="user",
                column_specs=_columns_from_dataclass_module(
                    "src.ingestion.adapters.l5_sdn", "SDNUser",
                ),
                primary_key=["user_id"],
            ),
        ]
    if adapter_kind == "l1_pdf":
        return [
            TableSpec(
                name="page",
                column_specs=_columns_from_dataclass_module(
                    "src.ingestion.adapters.l1_pdf", "L1PDFPage",
                ),
                primary_key=["document_id"],
            ),
        ]
    if adapter_kind == "l2_html":
        return [
            TableSpec(
                name="document",
                column_specs=_columns_from_dataclass_module(
                    "src.ingestion.adapters.l2_html", "L2Document",
                ),
                primary_key=["document_id"],
            ),
        ]
    if adapter_kind == "l1_excel":
        return [
            TableSpec(
                name="school",
                column_specs=_columns_from_dataclass_module(
                    "src.ingestion.adapters.l1_excel", "L1School",
                ),
                primary_key=["canonical_id"],
            ),
            TableSpec(
                name="metric",
                column_specs=_columns_from_dataclass_module(
                    "src.ingestion.adapters.l1_excel", "L1SchoolYearMetric",
                ),
                primary_key=["metric_id"],
            ),
            TableSpec(
                name="alias",
                column_specs=_columns_from_dataclass_module(
                    "src.ingestion.adapters.l1_excel", "L1Alias",
                ),
                primary_key=["alias_text", "canonical_id"],
            ),
        ]
    return []


def _columns_from_dataclass_module(module_path: str, klass: str) -> list[ColumnSpec]:
    mod = importlib.import_module(module_path)
    cls = getattr(mod, klass)
    out: list[ColumnSpec] = []
    for f in fields(cls):
        out.append(ColumnSpec(name=f.name, type=str(f.type), nullable=True))
    return out


# ----------------------------------------------------------------------
# Per-adapter result → CanonicalRecord stream
# ----------------------------------------------------------------------


def _records_from_result(result: object) -> Iterator[CanonicalRecord]:
    if isinstance(result, L5RedditResult):
        yield from _records_from_reddit(result)
        return
    if isinstance(result, L5SDNResult):
        yield from _records_from_sdn(result)
        return
    if isinstance(result, L1PDFResult):
        yield from _records_from_pdf(result)
        return
    if isinstance(result, L2IngestResult):
        yield from _records_from_html(result)
        return
    if isinstance(result, L1IngestResult):
        yield from _records_from_excel(result)
        return
    raise TypeError(
        f"unknown adapter result type: {type(result).__name__}",
    )


def _records_from_reddit(result: L5RedditResult) -> Iterator[CanonicalRecord]:
    # Order matches the test expectation: posts → users → comments (the test
    # asserts each bucket separately, so ordering across buckets is not
    # observable; within-bucket order matches the adapter's emit order).
    for user in result.users:
        yield CanonicalRecord(
            table_or_label="user",
            payload=user,
            primary_key=user.user_id,
            content_hash=_payload_hash(user),
        )
    for post in result.posts:
        yield CanonicalRecord(
            table_or_label="post",
            payload=post,
            primary_key=post.post_id,
            content_hash=_payload_hash(post),
        )
    for comment in result.comments:
        yield CanonicalRecord(
            table_or_label="comment",
            payload=comment,
            primary_key=comment.comment_id,
            content_hash=_payload_hash(comment),
        )


def _records_from_sdn(result: L5SDNResult) -> Iterator[CanonicalRecord]:
    for thread in result.threads:
        yield CanonicalRecord(
            table_or_label="thread",
            payload=thread,
            primary_key=thread.thread_id,
            content_hash=_payload_hash(thread),
        )
    for user in result.users:
        yield CanonicalRecord(
            table_or_label="user",
            payload=user,
            primary_key=user.user_id,
            content_hash=_payload_hash(user),
        )
    for post in result.posts:
        yield CanonicalRecord(
            table_or_label="post",
            payload=post,
            primary_key=post.post_id,
            content_hash=_payload_hash(post),
        )


def _records_from_pdf(result: L1PDFResult) -> Iterator[CanonicalRecord]:
    for page in result.pages:
        yield CanonicalRecord(
            table_or_label="page",
            payload=page,
            primary_key=page.document_id,
            content_hash=_payload_hash(page),
        )


def _records_from_html(result: L2IngestResult) -> Iterator[CanonicalRecord]:
    for doc in result.documents:
        yield CanonicalRecord(
            table_or_label="document",
            payload=doc,
            primary_key=doc.document_id,
            content_hash=_payload_hash(doc),
        )


def _records_from_excel(result: L1IngestResult) -> Iterator[CanonicalRecord]:
    for school in result.schools:
        yield CanonicalRecord(
            table_or_label="school",
            payload=school,
            primary_key=school.canonical_id,
            content_hash=_payload_hash(school),
        )
    for metric in result.metrics:
        yield CanonicalRecord(
            table_or_label="metric",
            payload=metric,
            primary_key=metric.metric_id,
            content_hash=_payload_hash(metric),
        )
    for alias in result.aliases:
        yield CanonicalRecord(
            table_or_label="alias",
            payload=alias,
            primary_key=f"{alias.alias_text}|{alias.canonical_id}",
            content_hash=_payload_hash(alias),
        )


def _payload_hash(payload: object) -> str:
    if is_dataclass(payload) and not isinstance(payload, type):
        canonical = repr(sorted(asdict(payload).items()))
    else:
        canonical = repr(payload)
    return content_hash_str(canonical)[:16] or sha256(
        canonical.encode("utf-8"),
    ).hexdigest()[:16]


def _payload_to_dict(payload: object) -> dict[str, Any]:
    if is_dataclass(payload) and not isinstance(payload, type):
        return {k: v for k, v in asdict(payload).items()}
    if hasattr(payload, "model_dump"):
        return payload.model_dump()  # type: ignore[no-any-return]
    raise TypeError(
        f"cannot dictify payload of type {type(payload).__name__}",
    )
