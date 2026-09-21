"""`get_docs_for_code(file_or_symbol, ...)` — reverse traversal of `DOC_SECTION_REFERENCES_CODE`."""

from __future__ import annotations

from dataclasses import dataclass

from tools.graphrag.store.client import EdgeQuery
from tools.graphrag.store.sqlite_client import SQLiteGraphClient
from tools.graphrag.types import EdgeType


@dataclass(frozen=True)
class DocReference:
    doc_section_id: str
    page_path: str
    anchor: str
    heading: str
    snippet: str


def get_docs_for_code(
    store: SQLiteGraphClient,
    file_or_symbol: str,
    *,
    limit: int = 20,
) -> list[DocReference]:
    """Given a CodeFile/Function/Class id (or source path), return DocSection nodes that reference it."""

    target_id = file_or_symbol
    if "/" in file_or_symbol and not file_or_symbol.startswith(("code:", "fn:", "cls:")):
        target_id = f"code:{file_or_symbol}"
    elif "." in file_or_symbol and not file_or_symbol.startswith(("fn:", "cls:", "code:")):
        node = store.get_node(f"fn:{file_or_symbol}") or store.get_node(f"cls:{file_or_symbol}")
        if node is not None:
            target_id = node.id

    edges = store.query_edges(
        EdgeQuery(edge_type=EdgeType.DOC_SECTION_REFERENCES_CODE, to_node_id=target_id)
    )
    out: list[DocReference] = []
    for edge in edges[:limit]:
        section = store.get_node(edge.from_node_id)
        if section is None:
            continue
        text = section.properties.get("text", "")
        snippet = text[:200] if isinstance(text, str) else ""
        page_id = str(section.properties.get("page_id") or "")
        page = store.get_node(page_id) if page_id else None
        out.append(
            DocReference(
                doc_section_id=section.id,
                page_path=(page.source_path if page else section.source_path) or "",
                anchor=str(section.properties.get("anchor") or ""),
                heading=str(section.properties.get("heading") or ""),
                snippet=snippet,
            )
        )
    return out
