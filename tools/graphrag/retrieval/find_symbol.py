"""`find_symbol(symbol, ...)` — exact / prefix / substring lookup on code-symbol names.

V1 uses the SQLite store's `node_type` filter + `properties_json` LIKE match. Cheap; works on
any-size repo we'll hit in V1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from tools.graphrag.store.client import NodeQuery
from tools.graphrag.store.sqlite_client import SQLiteGraphClient
from tools.graphrag.types import Node, NodeType

MatchKind = Literal["exact", "prefix", "substring"]

_DEFAULT_KINDS: tuple[NodeType, ...] = (
    NodeType.FUNCTION,
    NodeType.CLASS,
    NodeType.CODE_FILE,
    NodeType.CONFIG_KEY,
    NodeType.TEST_CASE,
)


@dataclass(frozen=True)
class SymbolMatch:
    node_id: str
    node_type: str
    qualified_name: str
    name: str
    source_path: str | None
    signature: str | None
    docstring: str | None
    start_line: int | None
    end_line: int | None
    match_kind: MatchKind


def _qualified_name(node: Node) -> str:
    qname = node.properties.get("qualified_name")
    if isinstance(qname, str):
        return qname
    key = node.properties.get("key")
    if isinstance(key, str):
        return key
    return node.id


def _short_name(node: Node) -> str:
    name = node.properties.get("name")
    if isinstance(name, str):
        return name
    return _qualified_name(node).rsplit(".", 1)[-1]


def find_symbol(
    store: SQLiteGraphClient,
    symbol: str,
    *,
    kind_filter: tuple[NodeType, ...] = (),
    limit: int = 10,
) -> list[SymbolMatch]:
    """Look up code symbols (`Function`, `Class`, `CodeFile`, `ConfigKey`, `TestCase`)."""

    if not symbol:
        return []
    types = kind_filter or _DEFAULT_KINDS
    candidates = store.query_nodes(NodeQuery(node_types=types))

    exacts: list[SymbolMatch] = []
    prefixes: list[SymbolMatch] = []
    substrings: list[SymbolMatch] = []

    needle = symbol
    needle_lower = symbol.lower()
    for node in candidates:
        qname = _qualified_name(node)
        short = _short_name(node)
        # Exact match (case-sensitive) on qualified name or short name.
        if needle in (qname, short):
            match = _to_match(node, qname, short, "exact")
            exacts.append(match)
            continue
        # Prefix match (case-sensitive).
        if qname.startswith(needle) or short.startswith(needle):
            prefixes.append(_to_match(node, qname, short, "prefix"))
            continue
        # Substring match (case-insensitive).
        if needle_lower in qname.lower() or needle_lower in short.lower():
            substrings.append(_to_match(node, qname, short, "substring"))

    ordered = exacts + prefixes + substrings
    return ordered[:limit]


def _to_match(node: Node, qname: str, short: str, kind: MatchKind) -> SymbolMatch:
    props = node.properties
    return SymbolMatch(
        node_id=node.id,
        node_type=node.node_type.value,
        qualified_name=qname,
        name=short,
        source_path=node.source_path,
        signature=_string_prop(props, "signature"),
        docstring=_string_prop(props, "docstring"),
        start_line=_int_prop(props, "start_line"),
        end_line=_int_prop(props, "end_line"),
        match_kind=kind,
    )


def _string_prop(props: dict[str, object], key: str) -> str | None:
    value = props.get(key)
    return value if isinstance(value, str) else None


def _int_prop(props: dict[str, object], key: str) -> int | None:
    value = props.get(key)
    return value if isinstance(value, int) else None
