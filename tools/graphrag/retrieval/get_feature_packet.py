"""`get_feature_packet(feature)` — return every DocPage under `docs/05-features/<slug>/`."""

from __future__ import annotations

from dataclasses import dataclass

from tools.graphrag.store.client import NodeQuery
from tools.graphrag.store.sqlite_client import SQLiteGraphClient
from tools.graphrag.types import NodeType

_ORDER_KEY = (
    "README.md",
    "context.md",
    "requirements.md",
    "plan.md",
    "api.md",
    "data.md",
    "state-machine.md",
    "test-plan.md",
    "decisions.md",
    "known-issues.md",
    "changelog.md",
)


@dataclass(frozen=True)
class FeaturePacketDocument:
    source_path: str
    title: str
    content: str


@dataclass(frozen=True)
class FeaturePacket:
    feature_id: str
    slug: str
    documents: list[FeaturePacketDocument]


def _slug_to_feature_id(slug: str) -> str:
    return f"feature:{slug}"


def _slug_from_feature_arg(feature: str) -> str:
    if feature.startswith("feature:"):
        return feature.removeprefix("feature:")
    return feature


def _doc_order_key(source_path: str) -> tuple[int, str]:
    name = source_path.rsplit("/", 1)[-1]
    try:
        return (_ORDER_KEY.index(name), name)
    except ValueError:
        return (len(_ORDER_KEY), name)


def get_feature_packet(store: SQLiteGraphClient, feature: str) -> FeaturePacket | None:
    slug = _slug_from_feature_arg(feature)
    feature_node = store.get_node(_slug_to_feature_id(slug))
    if feature_node is None:
        return None
    prefix = f"docs/05-features/{slug}/"
    pages = store.query_nodes(
        NodeQuery(node_type=NodeType.DOC_PAGE, source_path_prefix=prefix)
    )
    docs: list[FeaturePacketDocument] = []
    for page in sorted(pages, key=lambda p: _doc_order_key(p.source_path or "")):
        title = page.properties.get("title")
        if not isinstance(title, str):
            title = page.source_path or page.id
        # Pull section texts from the DocSection children to reconstruct readable content.
        section_query = NodeQuery(node_type=NodeType.DOC_SECTION, source_path_prefix=(page.source_path or "") + "#")
        section_nodes = store.query_nodes(section_query)
        section_nodes.sort(key=lambda n: int(n.properties.get("level") or 0))
        content_parts: list[str] = []
        for sn in section_nodes:
            heading = sn.properties.get("heading", "")
            text = sn.properties.get("text", "")
            level = sn.properties.get("level", 2)
            if isinstance(heading, str) and isinstance(text, str) and isinstance(level, int):
                content_parts.append("#" * level + " " + heading + "\n\n" + text)
        content = "\n\n".join(content_parts)
        docs.append(
            FeaturePacketDocument(
                source_path=page.source_path or "",
                title=title,
                content=content,
            )
        )
    return FeaturePacket(feature_id=feature_node.id, slug=slug, documents=docs)
