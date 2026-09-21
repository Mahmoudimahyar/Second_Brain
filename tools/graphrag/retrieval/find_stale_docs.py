"""`find_stale_docs(changed_files, ...)` — heuristic stale-doc detection by `last_modified_at` diff."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from tools.graphrag.store.client import EdgeQuery
from tools.graphrag.store.sqlite_client import SQLiteGraphClient
from tools.graphrag.types import EdgeType


@dataclass(frozen=True)
class StaleCandidate:
    doc_section_id: str
    page_path: str
    anchor: str
    referenced_code_path: str
    code_last_modified: datetime
    doc_last_modified: datetime
    days_stale: int


def find_stale_docs(
    store: SQLiteGraphClient,
    changed_files: list[str],
    *,
    days_threshold: int = 30,
) -> list[StaleCandidate]:
    """For each path in `changed_files`, return DocSection candidates older than the code."""

    out: list[StaleCandidate] = []
    for path in changed_files:
        code_id = path if path.startswith("code:") else f"code:{path}"
        code_node = store.get_node(code_id)
        if code_node is None or code_node.last_modified_at is None:
            continue
        # Reverse-traverse DOC_SECTION_REFERENCES_CODE → DocSection.
        for edge in store.query_edges(
            EdgeQuery(edge_type=EdgeType.DOC_SECTION_REFERENCES_CODE, to_node_id=code_node.id)
        ):
            section = store.get_node(edge.from_node_id)
            if section is None or section.last_modified_at is None:
                continue
            if section.last_modified_at >= code_node.last_modified_at:
                continue
            delta = code_node.last_modified_at - section.last_modified_at
            if delta.days < days_threshold:
                continue
            page_id = str(section.properties.get("page_id") or "")
            page = store.get_node(page_id) if page_id else None
            out.append(
                StaleCandidate(
                    doc_section_id=section.id,
                    page_path=(page.source_path if page else section.source_path) or "",
                    anchor=str(section.properties.get("anchor") or ""),
                    referenced_code_path=code_node.source_path or "",
                    code_last_modified=code_node.last_modified_at,
                    doc_last_modified=section.last_modified_at,
                    days_stale=delta.days,
                )
            )
    out.sort(key=lambda s: s.days_stale, reverse=True)
    return out
