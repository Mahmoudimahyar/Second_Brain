"""Repo indexer: walks `repo_root`, dispatches files to matching parsers, runs edge derivation,
writes everything to a `GraphClient` store.

CLI:

    python -m tools.graphrag.index --full              [--db ./data/graph/repo.db]
    python -m tools.graphrag.index --incremental       [--db ./data/graph/repo.db]
    python -m tools.graphrag.index --paths "docs/**/*.md"

Full mode rebuilds from scratch. Incremental mode compares each file's content-hash against the
prior snapshot and skips unchanged files (edges are always re-derived because they may depend on
cross-file changes).
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import structlog

from tools.graphrag.edges import derive_all_edges
from tools.graphrag.parsers import ALL_PARSERS, accepts_path
from tools.graphrag.store.client import NodeQuery, Snapshot
from tools.graphrag.store.sqlite_client import SQLiteGraphClient
from tools.graphrag.types import Node, ParseResult

log = structlog.get_logger(__name__)

# Skip these directories outright — never index them.
_SKIP_DIRS: tuple[str, ...] = (
    ".git",
    ".venv",
    "venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "data",
    "External Data",
    ".prefect",
    ".agent",
)


def _walk_repo(repo_root: Path, restrict_globs: tuple[str, ...] | None = None) -> Iterable[Path]:
    """Yield files under `repo_root`, skipping common build/cache dirs."""

    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(repo_root).parts
        if any(part in _SKIP_DIRS for part in rel_parts):
            continue
        rel = path.relative_to(repo_root).as_posix()
        if restrict_globs is not None and not any(
            fnmatch.fnmatch(rel, g) for g in restrict_globs
        ):
            continue
        yield path


def _dispatch_parsers(file_path: Path, repo_root: Path) -> ParseResult:
    """Run every matching parser on `file_path`; merge results."""

    repo_relative = file_path.relative_to(repo_root).as_posix()
    merged = ParseResult()
    for parser in ALL_PARSERS:
        if not accepts_path(parser, repo_relative):
            continue
        try:
            result = parser.parse(file_path, repo_root)
        except Exception as exc:
            parser_name = getattr(parser, "__name__", type(parser).__name__)
            merged.warnings.append(f"parser {parser_name} failed on {repo_relative}: {exc}")
            continue
        merged.nodes.extend(result.nodes)
        merged.edges.extend(result.edges)
        merged.warnings.extend(result.warnings)
    return merged


def _compute_snapshot_id(commit_sha: str | None, content_hashes: list[str]) -> str:
    """Deterministic ID for a snapshot: hash of commit SHA + sorted content hashes."""

    h = hashlib.sha256()
    if commit_sha:
        h.update(commit_sha.encode("utf-8"))
    h.update(b"|")
    for ch in sorted(content_hashes):
        h.update(ch.encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()[:16]


def _file_content_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def index_full(
    repo_root: Path,
    store: SQLiteGraphClient,
    *,
    restrict_globs: tuple[str, ...] | None = None,
    commit_sha: str | None = None,
) -> Snapshot:
    """Full reindex: re-parse every accepted file + derive every edge."""

    all_nodes: list[Node] = []
    intra_file_edges = []
    file_hashes: list[str] = []
    files_indexed = 0
    warnings: list[str] = []

    for file_path in _walk_repo(repo_root, restrict_globs):
        files_indexed += 1
        result = _dispatch_parsers(file_path, repo_root)
        all_nodes.extend(result.nodes)
        intra_file_edges.extend(result.edges)
        warnings.extend(result.warnings)
        file_hashes.append(_file_content_hash(file_path))

    derived_edges = derive_all_edges(all_nodes)
    all_edges = [*intra_file_edges, *derived_edges]

    snapshot_id = _compute_snapshot_id(commit_sha, file_hashes)
    snapshot = Snapshot(
        snapshot_id=snapshot_id,
        commit_sha=commit_sha,
        files_indexed=files_indexed,
        nodes_total=len(all_nodes),
        edges_total=len(all_edges),
        created_at=datetime.now(UTC),
        notes=f"full; warnings={len(warnings)}",
    )
    store.upsert_nodes(all_nodes, snapshot_id)
    store.upsert_edges(all_edges, snapshot_id)
    store.record_snapshot(snapshot)
    log.info(
        "graphrag.index.full",
        files=files_indexed,
        nodes=len(all_nodes),
        edges=len(all_edges),
        warnings=len(warnings),
        snapshot=snapshot_id,
    )
    return snapshot


def index_incremental(
    repo_root: Path,
    store: SQLiteGraphClient,
    *,
    restrict_globs: tuple[str, ...] | None = None,
    commit_sha: str | None = None,
) -> Snapshot:
    """Incremental reindex: only re-parse files whose content_hash differs from the last snapshot.

    Edges are always re-derived because cross-file edges may have changed even if the source
    files appear unchanged.
    """

    latest = store.latest_snapshot()
    if latest is None:
        return index_full(repo_root, store, restrict_globs=restrict_globs, commit_sha=commit_sha)

    # Load all nodes from the latest snapshot; keep them unless their file changed.
    prior_nodes = store.query_nodes(NodeQuery(snapshot_id=latest.snapshot_id))
    prior_by_path: dict[str, list[Node]] = {}
    for node in prior_nodes:
        if node.source_path is None:
            continue
        # Strip any anchor suffix (DocSection paths contain `#anchor`).
        path = node.source_path.split("#", 1)[0]
        prior_by_path.setdefault(path, []).append(node)

    fresh_nodes: list[Node] = []
    intra_file_edges = []
    file_hashes: list[str] = []
    files_indexed = 0
    warnings: list[str] = []
    seen_paths: set[str] = set()

    for file_path in _walk_repo(repo_root, restrict_globs):
        rel = file_path.relative_to(repo_root).as_posix()
        seen_paths.add(rel)
        files_indexed += 1
        current_hash = _file_content_hash(file_path)
        file_hashes.append(current_hash)
        # Try to reuse prior nodes if the file hash matches AND no prior node mismatches.
        prior = prior_by_path.get(rel, [])
        if prior and all(
            n.content_hash is None or n.content_hash == current_hash or n.source_path != rel
            for n in prior
        ):
            # File appears unchanged at the byte level. Reuse prior nodes.
            fresh_nodes.extend(prior)
            continue
        result = _dispatch_parsers(file_path, repo_root)
        fresh_nodes.extend(result.nodes)
        intra_file_edges.extend(result.edges)
        warnings.extend(result.warnings)

    # Bring along DocSection / Function / etc. nodes whose owning file we didn't see
    # (because it doesn't match restrict_globs). Skipping these would corrupt cross-file edges.
    for path, prior in prior_by_path.items():
        if path not in seen_paths and restrict_globs is None:
            fresh_nodes.extend(prior)

    derived_edges = derive_all_edges(fresh_nodes)
    all_edges = [*intra_file_edges, *derived_edges]

    snapshot_id = _compute_snapshot_id(commit_sha, file_hashes)
    snapshot = Snapshot(
        snapshot_id=snapshot_id,
        commit_sha=commit_sha,
        files_indexed=files_indexed,
        nodes_total=len(fresh_nodes),
        edges_total=len(all_edges),
        created_at=datetime.now(UTC),
        notes=f"incremental from={latest.snapshot_id}; warnings={len(warnings)}",
    )
    store.upsert_nodes(fresh_nodes, snapshot_id)
    store.upsert_edges(all_edges, snapshot_id)
    store.record_snapshot(snapshot)
    log.info(
        "graphrag.index.incremental",
        prior=latest.snapshot_id,
        files=files_indexed,
        nodes=len(fresh_nodes),
        edges=len(all_edges),
        warnings=len(warnings),
        snapshot=snapshot_id,
    )
    return snapshot


def index_command(argv: list[str] | None = None) -> int:
    """CLI entrypoint (referenced from pyproject.toml `[project.scripts]`)."""

    parser = argparse.ArgumentParser(prog="graphrag-index")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--full", action="store_true", help="full reindex (rebuild)")
    mode.add_argument("--incremental", action="store_true", help="reindex only changed files")
    parser.add_argument("--db", default="./data/graph/repo.db", help="path to SQLite store")
    parser.add_argument("--repo", default=".", help="repo root")
    parser.add_argument(
        "--paths",
        action="append",
        default=[],
        help="restrict indexing to glob (may be repeated; default = whole repo)",
    )
    parser.add_argument("--commit-sha", default=None, help="commit SHA to embed in snapshot ID")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo).resolve()
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    restrict = tuple(args.paths) if args.paths else None

    store = SQLiteGraphClient(db_path)
    try:
        if args.full:
            snapshot = index_full(repo_root, store, restrict_globs=restrict, commit_sha=args.commit_sha)
        else:
            snapshot = index_incremental(repo_root, store, restrict_globs=restrict, commit_sha=args.commit_sha)
    finally:
        store.close()

    sys.stdout.write(
        f"snapshot={snapshot.snapshot_id} files={snapshot.files_indexed} "
        f"nodes={snapshot.nodes_total} edges={snapshot.edges_total}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(index_command())
