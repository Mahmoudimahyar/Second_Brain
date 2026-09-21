"""Markdown parser: emits `DocPage` + `DocSection` nodes per `tools/graphrag/schema.md`.

Behavior:

  - Every `.md` file → exactly one `DocPage` node.
  - Each `#`, `##`, `###` heading in the file → one `DocSection` node, with `level`, `heading`,
    `text` (everything until the next heading of `level <= current`), and an `anchor` slug.
  - `DOC_PAGE_HAS_SECTION` edges from the `DocPage` to each `DocSection`.
  - Optional YAML frontmatter (between two `---` delimiters at the very start) is parsed
    into `DocPage.properties["frontmatter"]`.
  - The first H1 (if present) is used as `DocPage.properties["title"]`; falls back to the
    filename stem.

This parser is pure: it does not touch the filesystem outside reading the one file passed in,
and does not emit timestamps or snapshot IDs.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import yaml

from tools.graphrag.types import (
    Edge,
    EdgeType,
    Node,
    NodeType,
    ParseResult,
    slugify_heading,
    slugify_path,
)

ACCEPTS: tuple[str, ...] = ("*.md", "*.markdown")

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse(file_path: Path, repo_root: Path) -> ParseResult:
    """Parse a single markdown file into `DocPage` + `DocSection` nodes + structural edges."""

    text = file_path.read_text(encoding="utf-8")
    repo_relative = file_path.relative_to(repo_root).as_posix()
    content_hash = _hash_text(text)

    frontmatter, body = _strip_frontmatter(text)
    title = _first_h1(body) or file_path.stem
    sections = _extract_sections(body)

    page_id = f"doc:{slugify_path(repo_relative)}"
    page = Node(
        id=page_id,
        node_type=NodeType.DOC_PAGE,
        source_path=repo_relative,
        content_hash=content_hash,
        properties={
            "title": title,
            "frontmatter": frontmatter,
            "byte_size": len(text.encode("utf-8")),
            "section_count": len(sections),
        },
    )

    nodes: list[Node] = [page]
    edges: list[Edge] = []
    seen_anchors: dict[str, int] = {}
    warnings: list[str] = []

    for level, heading, body_text in sections:
        anchor = slugify_heading(heading)
        if anchor in seen_anchors:
            seen_anchors[anchor] += 1
            anchor = f"{anchor}-{seen_anchors[anchor]}"
            warnings.append(f"duplicate heading anchor in {repo_relative}: {heading!r}")
        else:
            seen_anchors[anchor] = 0
        section_id = f"{page_id}#{anchor}"
        section_node = Node(
            id=section_id,
            node_type=NodeType.DOC_SECTION,
            source_path=f"{repo_relative}#{anchor}",
            content_hash=_hash_text(body_text),
            properties={
                "level": level,
                "heading": heading,
                "text": body_text,
                "anchor": anchor,
                "page_id": page_id,
            },
        )
        nodes.append(section_node)
        edges.append(
            Edge(
                id=f"edge:{page_id}-has-section-{section_id}",
                edge_type=EdgeType.DOC_PAGE_HAS_SECTION,
                from_node_id=page_id,
                to_node_id=section_id,
                properties={"section_order": len(edges)},
            )
        )

    return ParseResult(nodes=nodes, edges=edges, warnings=warnings)


def _hash_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _strip_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Pull a YAML frontmatter block (if any) and return `(frontmatter_dict, body_without_it)`."""

    m = _FRONTMATTER_RE.match(text)
    if not m:
        return ({}, text)
    fm_raw = m.group(1)
    try:
        parsed = yaml.safe_load(fm_raw) or {}
    except yaml.YAMLError:
        return ({}, text)
    if not isinstance(parsed, dict):
        return ({}, text)
    return (parsed, text[m.end() :])


def _first_h1(body: str) -> str | None:
    for match in _HEADING_RE.finditer(body):
        if len(match.group(1)) == 1:
            return match.group(2).strip()
    return None


def _extract_sections(body: str) -> list[tuple[int, str, str]]:
    """Walk H1/H2/H3 headings and capture each section's body up to the next heading of equal-or-shallower level."""

    matches = list(_HEADING_RE.finditer(body))
    sections: list[tuple[int, str, str]] = []
    for i, match in enumerate(matches):
        level = len(match.group(1))
        heading = match.group(2).strip()
        start = match.end()
        # End at the next heading of level <= current.
        end = len(body)
        for next_match in matches[i + 1 :]:
            if len(next_match.group(1)) <= level:
                end = next_match.start()
                break
        section_text = body[start:end].strip()
        sections.append((level, heading, section_text))
    return sections
