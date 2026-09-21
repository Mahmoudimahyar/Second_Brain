"""`get_code_for_doc(doc_path, ...)` — forward traversal of `DOC_SECTION_REFERENCES_CODE`."""

from __future__ import annotations

from dataclasses import dataclass

from tools.graphrag.store.client import EdgeQuery, NodeQuery
from tools.graphrag.store.sqlite_client import SQLiteGraphClient
from tools.graphrag.types import EdgeType, NodeType


@dataclass(frozen=True)
class CodeReference:
    source_path: str
    name: str
    kind: str
    start_line: int | None
    end_line: int | None
    referenced_in_section: str


def get_code_for_doc(
    store: SQLiteGraphClient,
    doc_path: str,
    *,
    include_subsections: bool = True,
) -> list[CodeReference]:
    """Given a DocPage source_path or `doc:` id, return Code targets referenced from its sections."""

    page_id = doc_path
    if not doc_path.startswith("doc:"):
        page_id = f"doc:{doc_path.replace('/', ':')}"
    page = store.get_node(page_id)
    if page is None:
        return []

    section_ids: list[str] = []
    if include_subsections and page.source_path:
        sections = store.query_nodes(
            NodeQuery(node_type=NodeType.DOC_SECTION, source_path_prefix=page.source_path + "#")
        )
        section_ids = [s.id for s in sections]
    else:
        section_ids = [page.id]

    out: list[CodeReference] = []
    seen: set[str] = set()
    for sec_id in section_ids:
        section = store.get_node(sec_id)
        heading = str(section.properties.get("heading") if section else "") or ""
        for edge in store.query_edges(
            EdgeQuery(edge_type=EdgeType.DOC_SECTION_REFERENCES_CODE, from_node_id=sec_id)
        ):
            target = store.get_node(edge.to_node_id)
            if target is None or target.id in seen:
                continue
            seen.add(target.id)
            props = target.properties
            kind = target.node_type.value
            name = (
                str(props.get("name") or props.get("qualified_name") or target.source_path or target.id)
            )
            start = props.get("start_line")
            end = props.get("end_line")
            out.append(
                CodeReference(
                    source_path=target.source_path or "",
                    name=name,
                    kind=kind,
                    start_line=int(start) if isinstance(start, int) else None,
                    end_line=int(end) if isinstance(end, int) else None,
                    referenced_in_section=heading,
                )
            )
    return out
