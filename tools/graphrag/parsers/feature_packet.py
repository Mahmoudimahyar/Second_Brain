"""Feature-packet parser: emits `Feature` + `Requirement` + `AcceptanceCriterion` nodes.

Scope: files under `docs/05-features/<slug>/` (excluding `TEMPLATE/`). Three file kinds are
recognized:

  * `README.md`        → one `Feature` node (slug from directory; name from first H1; status
                         from `**Status:** ...` line).
  * `requirements.md`  → `Requirement` nodes for every `FR-N` / `FR-N.M` / `NFR-N` pattern.
  * `test-plan.md`     → `AcceptanceCriterion` nodes for every `### AC-N — ...` heading, with
                         `linked_requirement_ids` extracted from any `(FR-X.Y)` references.

Cross-file edges (FEATURE_HAS_REQUIREMENT, REQUIREMENT_HAS_ACCEPTANCE_CRITERION,
FEATURE_DOCUMENTED_BY) are derived in `tools/graphrag/edges.py` (Phase 2), not here. This
parser stores the `feature_slug` on each Requirement / AC so the edge deriver can join them.

Pure function: same input → same output. No filesystem side effects beyond reading the one file.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from tools.graphrag.types import (
    Edge,
    Node,
    NodeType,
    ParseResult,
)

ACCEPTS: tuple[str, ...] = (
    "docs/05-features/*/README.md",
    "docs/05-features/*/requirements.md",
    "docs/05-features/*/test-plan.md",
)

# Match bold-marker on FR / NFR IDs:
#   - **FR-1**         (rare; usually a sub-id follows)
#   - **FR-1.2**       (canonical sub-item)
#   - **NFR-3**        (canonical NFR; title may follow inside the bold)
_REQ_LINE_RE = re.compile(
    r"^\s*[-*]\s*\*\*(?P<id>(?:N?FR)-\d+(?:\.\d+)?)"
    r"(?:\s+(?P<inline_title>[^*]+?))?\*\*"
    r"\s*[:—\-]?\s*"
    r"(?P<description>.+?)\s*$",
    re.MULTILINE,
)

_REQ_HEADING_RE = re.compile(
    r"""
    ^\#{2,3}\s+
    (?P<id>(?:N?FR)-\d+(?:\.\d+)?)
    \s*[—\-:]?\s*
    (?P<title>[^\n]+?)\s*$
    """,
    re.MULTILINE | re.VERBOSE,
)

_AC_HEADING_RE = re.compile(
    r"""
    ^\#{2,3}\s+
    AC-(?P<num>\d+)
    \s*[—\-:]?\s*
    (?P<title>.+?)\s*$
    """,
    re.MULTILINE | re.VERBOSE,
)

_FR_REF_INLINE_RE = re.compile(r"\((?P<refs>(?:N?FR-\d+(?:\.\d+)?(?:\s*,\s*)?)+)\)")

_STATUS_LINE_RE = re.compile(
    r"^\s*\*{0,2}\s*Status:?\s*\*{0,2}\s*[—:\-]?\s*(?P<status>.+?)\s*$",
    re.MULTILINE | re.IGNORECASE,
)

_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def _normalize_status(raw: str) -> str:
    """Map a free-form status string to the canonical enum (proposed/in-progress/complete/deferred)."""

    s = raw.strip().lower()
    if any(k in s for k in ("proposed", "draft", "spec only", "spec-only", "specced", "pending")):
        return "proposed"
    if any(k in s for k in ("in progress", "in-progress", "implementing", "active")):
        return "in-progress"
    if any(k in s for k in ("complete", "done", "shipped", "accepted", "ratified")):
        return "complete"
    if any(k in s for k in ("deferred", "blocked", "abandoned", "skipped")):
        return "deferred"
    return "proposed"


def _slug_from_feature_path(repo_relative: str) -> str | None:
    """Return the feature slug (e.g., '01-slice-trust-tier-canonicalize') for any path under that feature, or None."""

    parts = repo_relative.replace("\\", "/").split("/")
    if len(parts) >= 3 and parts[0] == "docs" and parts[1] == "05-features":
        slug = parts[2]
        if slug == "TEMPLATE":
            return None
        return slug
    return None


def _hash_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def parse(file_path: Path, repo_root: Path) -> ParseResult:
    """Dispatch on filename. Returns nodes only — edges are derived in Phase 2 `edges.py`."""

    repo_relative = file_path.relative_to(repo_root).as_posix()
    slug = _slug_from_feature_path(repo_relative)
    if slug is None:
        return ParseResult()

    text = file_path.read_text(encoding="utf-8")
    name = file_path.name

    if name == "README.md":
        return _parse_readme(text, slug, repo_relative)
    if name == "requirements.md":
        return _parse_requirements(text, slug, repo_relative)
    if name == "test-plan.md":
        return _parse_test_plan(text, slug, repo_relative)
    return ParseResult()


def _parse_readme(text: str, slug: str, repo_relative: str) -> ParseResult:
    """Emit one `Feature` node from `<slice>/README.md`."""

    h1_match = _H1_RE.search(text)
    if h1_match:
        name_raw = h1_match.group(1).strip()
        name = re.sub(r"^Feature:\s*", "", name_raw, flags=re.IGNORECASE)
    else:
        name = slug

    status = "proposed"
    status_match = _STATUS_LINE_RE.search(text)
    if status_match:
        status = _normalize_status(status_match.group("status"))

    props: dict[str, Any] = {"slug": slug, "name": name, "status": status}
    feature_node = Node(
        id=f"feature:{slug}",
        node_type=NodeType.FEATURE,
        source_path=repo_relative,
        content_hash=_hash_text(text),
        properties=props,
    )
    return ParseResult(nodes=[feature_node])


def _parse_requirements(text: str, slug: str, repo_relative: str) -> ParseResult:
    """Emit `Requirement` nodes for every FR-/NFR pattern found."""

    nodes: list[Node] = []
    edges: list[Edge] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()

    headings: dict[str, str] = {}
    for match in _REQ_HEADING_RE.finditer(text):
        req_id = match.group("id")
        headings[req_id] = match.group("title").strip()

    for match in _REQ_LINE_RE.finditer(text):
        req_id = match.group("id")
        if req_id in seen_ids:
            warnings.append(f"duplicate requirement id in {repo_relative}: {req_id}")
            continue
        seen_ids.add(req_id)
        kind = "non-functional" if req_id.startswith("NFR") else "functional"
        inline_title = (match.group("inline_title") or "").strip()
        description = match.group("description").strip()
        title = inline_title or headings.get(req_id, description[:60])
        nodes.append(
            Node(
                id=f"req:{slug}:{req_id}",
                node_type=NodeType.REQUIREMENT,
                source_path=repo_relative,
                content_hash=_hash_text(description),
                properties={
                    "req_id": req_id,
                    "feature_slug": slug,
                    "title": title,
                    "description": description,
                    "kind": kind,
                },
            )
        )

    return ParseResult(nodes=nodes, edges=edges, warnings=warnings)


def _parse_test_plan(text: str, slug: str, repo_relative: str) -> ParseResult:
    """Emit `AcceptanceCriterion` nodes for every `### AC-N — ...` heading."""

    nodes: list[Node] = []
    warnings: list[str] = []
    matches = list(_AC_HEADING_RE.finditer(text))
    seen_ids: set[str] = set()

    for i, match in enumerate(matches):
        ac_id = f"AC-{match.group('num')}"
        if ac_id in seen_ids:
            warnings.append(f"duplicate AC id in {repo_relative}: {ac_id}")
            continue
        seen_ids.add(ac_id)

        title_raw = match.group("title").strip()
        ref_match = _FR_REF_INLINE_RE.search(title_raw)
        linked_refs: list[str] = []
        if ref_match:
            for token in ref_match.group("refs").split(","):
                stripped = token.strip()
                if stripped:
                    linked_refs.append(stripped)
            title_clean = _FR_REF_INLINE_RE.sub("", title_raw).strip(" `")
        else:
            title_clean = title_raw

        section_start = match.end()
        section_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        description = text[section_start:section_end].strip()

        nodes.append(
            Node(
                id=f"ac:{slug}:{ac_id}",
                node_type=NodeType.ACCEPTANCE_CRITERION,
                source_path=repo_relative,
                content_hash=_hash_text(description),
                properties={
                    "ac_id": ac_id,
                    "feature_slug": slug,
                    "title": title_clean,
                    "description": description,
                    "linked_requirement_ids": linked_refs,
                },
            )
        )

    return ParseResult(nodes=nodes, warnings=warnings)
