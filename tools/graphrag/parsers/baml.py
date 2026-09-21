"""BAML prompt parser (V1 stub).

No `.baml` files exist yet in the repo — V1 product engine prompts (per ADR-004) will live under
`src/prompts/*.baml` when the gateway lands. For now this parser ACCEPTS the path glob but emits
no nodes. The stub guarantees that future BAML files don't crash the indexer + holds the slot in
the parser registry.

When the V1 product engine prompts land, this module will be filled in to emit `Prompt` nodes
with `prompt_id`, `prompt_version`, and `schema_hash` per `tools/graphrag/schema.md`.
"""

from __future__ import annotations

from pathlib import Path

from tools.graphrag.types import ParseResult

ACCEPTS: tuple[str, ...] = ("src/prompts/*.baml",)


def parse(file_path: Path, repo_root: Path) -> ParseResult:
    # Stub. Returns empty until BAML files exist + the parser is implemented in V1.x.
    _ = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
    return ParseResult()
