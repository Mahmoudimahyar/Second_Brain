"""Parsers for the repo MCP context server.

One module per content kind. All parsers expose a `parse(file_path) -> ParseResult` function and
declare their `ACCEPTS` glob patterns. See `tools/graphrag/architecture.md` for the design.

The `ALL_PARSERS` tuple is consumed by the indexer (Phase 3) to dispatch files to every parser
whose ACCEPTS pattern matches. Multiple parsers may match a single file (e.g., markdown.py +
feature_packet.py both run on `docs/05-features/<slug>/README.md`).
"""

from __future__ import annotations

from tools.graphrag.parsers import (
    adr,
    baml,
    config,
    context_pack,
    feature_packet,
    known_issues,
    markdown,
    python_code,
    test_file,
)
from tools.graphrag.parsers.base import RepoParser, accepts_path

ALL_PARSERS: tuple[RepoParser, ...] = (
    markdown,
    feature_packet,
    adr,
    python_code,
    test_file,
    known_issues,
    config,
    context_pack,
    baml,
)

__all__ = ["ALL_PARSERS", "RepoParser", "accepts_path"]
