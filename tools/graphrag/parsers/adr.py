"""ADR parser: emits one `ADR` node per `docs/11-decisions/ADR-*.md`.

Captures `status`, `date`, `decision_summary` (first paragraph of `## Decision`), and
`affects_modules` (backtick-wrapped paths from `## Related code`). The ADR ID + title come
from the H1 (e.g., `# ADR-003: Extraction Stack — 5-Pass Architecture`).

Status enum: `proposed` / `accepted` / `deprecated` / `pending`.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from tools.graphrag.parsers._util import hash_text
from tools.graphrag.types import Node, NodeType, ParseResult

ACCEPTS: tuple[str, ...] = ("docs/11-decisions/ADR-*.md",)

_H1_RE = re.compile(r"^#\s+(?P<rest>ADR-(?P<num>\d+)[:\s—\-].*?)\s*$", re.MULTILINE)
_STATUS_RE = re.compile(
    r"^\s*Status\s*:\s*\*{0,2}(?P<status>[A-Za-z\-]+)\*{0,2}",
    re.MULTILINE | re.IGNORECASE,
)
_DATE_RE = re.compile(r"^\s*Date\s*:\s*(?P<date>\d{4}-\d{2}-\d{2})", re.MULTILINE | re.IGNORECASE)
_DECISION_RE = re.compile(r"^##\s+Decision\s*$\n+(.+?)(?=\n##\s|\Z)", re.MULTILINE | re.DOTALL)
_RELATED_CODE_RE = re.compile(
    r"^##\s+Related code\s*$\n+(.+?)(?=\n##\s|\Z)",
    re.MULTILINE | re.DOTALL,
)
_BACKTICK_PATH_RE = re.compile(r"`([a-zA-Z0-9_./\-]+\.(?:py|md|toml|json|yaml|yml|sql|baml))`")


def _normalize_status(raw: str) -> str:
    s = raw.strip().lower()
    if s in {"accepted", "ratified", "complete", "done"}:
        return "accepted"
    if s in {"deprecated", "superseded"}:
        return "deprecated"
    if s in {"pending", "deferred", "tbd"}:
        return "pending"
    return "proposed"


def _first_paragraph(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    parts = re.split(r"\n\s*\n", cleaned, maxsplit=1)
    return parts[0].strip()


def _extract_affects_modules(related_code_section: str) -> list[str]:
    paths: list[str] = []
    for match in _BACKTICK_PATH_RE.finditer(related_code_section):
        path = match.group(1)
        if path not in paths:
            paths.append(path)
    return paths


def parse(file_path: Path, repo_root: Path) -> ParseResult:
    text = file_path.read_text(encoding="utf-8")
    repo_relative = file_path.relative_to(repo_root).as_posix()

    h1 = _H1_RE.search(text)
    if not h1:
        return ParseResult(warnings=[f"no ADR H1 found in {repo_relative}"])

    adr_id = f"ADR-{h1.group('num').zfill(3)}"
    title = h1.group("rest").strip()

    status_match = _STATUS_RE.search(text)
    status = _normalize_status(status_match.group("status")) if status_match else "proposed"

    date_match = _DATE_RE.search(text)
    parsed_date: date | None = None
    if date_match:
        try:
            parsed_date = date.fromisoformat(date_match.group("date"))
        except ValueError:
            parsed_date = None

    decision_match = _DECISION_RE.search(text)
    decision_summary = _first_paragraph(decision_match.group(1)) if decision_match else ""

    related_code_match = _RELATED_CODE_RE.search(text)
    affects_modules: list[str] = (
        _extract_affects_modules(related_code_match.group(1)) if related_code_match else []
    )

    props: dict[str, Any] = {
        "adr_id": adr_id,
        "title": title,
        "status": status,
        "date": parsed_date.isoformat() if parsed_date else None,
        "decision_summary": decision_summary,
        "affects_modules": affects_modules,
    }

    node = Node(
        id=f"adr:{adr_id}",
        node_type=NodeType.ADR,
        source_path=repo_relative,
        content_hash=hash_text(text),
        properties=props,
    )
    return ParseResult(nodes=[node])
