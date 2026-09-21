"""Context-pack parser: emits `ContextPack` nodes from `docs/14-context-packs/<pack>/README.md`.

A pack is any subdirectory of `docs/14-context-packs/` (the root README.md is NOT a pack — it
documents the system). The pack's `purpose` is the first non-empty paragraph of its README.
"""

from __future__ import annotations

import re
from pathlib import Path

from tools.graphrag.parsers._util import hash_text
from tools.graphrag.types import Node, NodeType, ParseResult

ACCEPTS: tuple[str, ...] = ("docs/14-context-packs/*/README.md",)

_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def _pack_name_from_path(repo_relative: str) -> str | None:
    parts = repo_relative.replace("\\", "/").split("/")
    # docs/14-context-packs/<pack>/README.md  → 4 parts; pack name = parts[2].
    # docs/14-context-packs/README.md         → 3 parts; this is the root README, not a pack.
    if (
        len(parts) >= 4
        and parts[0] == "docs"
        and parts[1] == "14-context-packs"
        and parts[-1] == "README.md"
    ):
        return parts[2]
    return None


def _first_paragraph(text: str) -> str:
    stripped_lines: list[str] = []
    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        if not line.strip():
            if stripped_lines:
                break
            continue
        stripped_lines.append(line.strip())
    return " ".join(stripped_lines).strip()


def parse(file_path: Path, repo_root: Path) -> ParseResult:
    text = file_path.read_text(encoding="utf-8")
    repo_relative = file_path.relative_to(repo_root).as_posix()
    pack_name = _pack_name_from_path(repo_relative)
    if pack_name is None:
        return ParseResult()

    h1 = _H1_RE.search(text)
    title = h1.group(1).strip() if h1 else pack_name
    purpose = _first_paragraph(text)

    node = Node(
        id=f"pack:{pack_name}",
        node_type=NodeType.CONTEXT_PACK,
        source_path=repo_relative,
        content_hash=hash_text(text),
        properties={
            "pack_name": pack_name,
            "title": title,
            "purpose": purpose,
        },
    )
    return ParseResult(nodes=[node])
