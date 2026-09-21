"""Known-issues parser: emits `KnownIssue` nodes from `**/known-issues.md` markdown tables.

Tables have at least: ID | Issue | Category | Severity | (workaround?) | (resolution plan?).
Rows whose ID column doesn't match `KI-\\d+` are skipped (e.g., the empty-placeholder row).
The `feature_slug` is inferred from the file path (`docs/05-features/<slug>/known-issues.md`).
For repo-wide known-issues files (not under a slice), `feature_slug` is `None`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tools.graphrag.parsers._util import hash_text
from tools.graphrag.types import Node, NodeType, ParseResult

ACCEPTS: tuple[str, ...] = (
    "docs/05-features/*/known-issues.md",
    "docs/**/known-issues.md",
)

_KI_ID_RE = re.compile(r"^\*?\*?KI-(\d+)\*?\*?$", re.IGNORECASE)
_SEVERITY_VALUES = {"low", "med", "medium", "high", "critical"}


def _slug_from_path(repo_relative: str) -> str | None:
    parts = repo_relative.replace("\\", "/").split("/")
    if len(parts) >= 3 and parts[0] == "docs" and parts[1] == "05-features":
        slug = parts[2]
        if slug == "TEMPLATE":
            return None
        return slug
    return None


def _split_table_row(line: str) -> list[str]:
    """Split a `| a | b | c |` row into trimmed cells. Returns empty list for non-rows."""

    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return []
    # Drop the leading + trailing empty cells from the pipe pairs.
    cells = [c.strip() for c in stripped.strip("|").split("|")]
    return cells


def _is_separator_row(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-+:?", c) for c in cells if c)


def _extract_tables(text: str) -> list[list[list[str]]]:
    """Find markdown tables: lists of [header_cells, *data_rows]."""

    tables: list[list[list[str]]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        cells = _split_table_row(lines[i])
        if len(cells) >= 2 and i + 1 < len(lines):
            sep = _split_table_row(lines[i + 1])
            if len(sep) == len(cells) and _is_separator_row(sep):
                rows: list[list[str]] = [cells]
                j = i + 2
                while j < len(lines):
                    data = _split_table_row(lines[j])
                    if len(data) != len(cells):
                        break
                    rows.append(data)
                    j += 1
                if len(rows) > 1:
                    tables.append(rows)
                i = j
                continue
        i += 1
    return tables


def _normalize_severity(raw: str) -> str:
    s = raw.strip().lower()
    if s in {"med", "medium"}:
        return "med"
    if s in _SEVERITY_VALUES:
        return s
    return "med"


def parse(file_path: Path, repo_root: Path) -> ParseResult:
    text = file_path.read_text(encoding="utf-8")
    repo_relative = file_path.relative_to(repo_root).as_posix()
    slug = _slug_from_path(repo_relative)
    nodes: list[Node] = []
    warnings: list[str] = []

    for table in _extract_tables(text):
        header = [c.lower() for c in table[0]]
        try:
            id_col = header.index("id")
        except ValueError:
            continue
        issue_col = _find_col(header, ("issue", "summary"))
        category_col = _find_col(header, ("category", "kind", "type"))
        severity_col = _find_col(header, ("severity", "priority"))
        workaround_col = _find_col(header, ("workaround",))
        resolution_col = _find_col(header, ("resolution plan", "resolution", "plan"))

        for row in table[1:]:
            cell_id = row[id_col]
            m = _KI_ID_RE.match(cell_id)
            if not m:
                continue
            ki_id = f"KI-{m.group(1).zfill(3)}"
            description = row[issue_col] if issue_col is not None else ""
            category = row[category_col] if category_col is not None else "Other"
            severity_raw = row[severity_col] if severity_col is not None else "med"
            workaround = row[workaround_col] if workaround_col is not None else ""
            resolution = row[resolution_col] if resolution_col is not None else ""

            if not description or description.strip() in {"TBD", "(empty placeholder)", "—"}:
                continue

            props: dict[str, Any] = {
                "ki_id": ki_id,
                "feature_slug": slug,
                "severity": _normalize_severity(severity_raw),
                "category": category.strip(),
                "description": description.strip(),
                "workaround": workaround.strip(),
                "resolution_plan": resolution.strip(),
            }
            node_id = f"ki:{slug}:{ki_id}" if slug else f"ki:repo:{ki_id}"
            nodes.append(
                Node(
                    id=node_id,
                    node_type=NodeType.KNOWN_ISSUE,
                    source_path=repo_relative,
                    content_hash=hash_text(description),
                    properties=props,
                )
            )

    return ParseResult(nodes=nodes, warnings=warnings)


def _find_col(header: list[str], aliases: tuple[str, ...]) -> int | None:
    for alias in aliases:
        if alias in header:
            return header.index(alias)
    return None
