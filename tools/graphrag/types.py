"""Node, Edge, and shared type definitions for the repo MCP context server.

Schema source of truth: `tools/graphrag/schema.md`.
Parsers emit `Node` / `Edge` records; the indexer assigns `snapshot_id` + timestamps before storage.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class NodeType(StrEnum):
    """All node types this parser layer can emit. See `tools/graphrag/schema.md`."""

    DOC_PAGE = "DocPage"
    DOC_SECTION = "DocSection"
    FEATURE = "Feature"
    REQUIREMENT = "Requirement"
    ACCEPTANCE_CRITERION = "AcceptanceCriterion"
    CODE_FILE = "CodeFile"
    FUNCTION = "Function"
    CLASS = "Class"
    CONFIG_KEY = "ConfigKey"
    TEST_FILE = "TestFile"
    TEST_CASE = "TestCase"
    ADR = "ADR"
    KNOWN_ISSUE = "KnownIssue"
    PROMPT = "Prompt"
    CONTEXT_PACK = "ContextPack"


class EdgeType(StrEnum):
    """All edge types this parser layer can emit. See `tools/graphrag/schema.md`."""

    DOC_PAGE_HAS_SECTION = "DOC_PAGE_HAS_SECTION"
    FILE_HAS_FUNCTION = "FILE_HAS_FUNCTION"
    FILE_HAS_CLASS = "FILE_HAS_CLASS"
    CLASS_HAS_METHOD = "CLASS_HAS_METHOD"
    TEST_FILE_HAS_CASE = "TEST_FILE_HAS_CASE"
    FEATURE_HAS_REQUIREMENT = "FEATURE_HAS_REQUIREMENT"
    REQUIREMENT_HAS_ACCEPTANCE_CRITERION = "REQUIREMENT_HAS_ACCEPTANCE_CRITERION"
    FEATURE_DOCUMENTED_BY = "FEATURE_DOCUMENTED_BY"
    FEATURE_IMPLEMENTED_BY = "FEATURE_IMPLEMENTED_BY"
    DOC_SECTION_REFERENCES_CODE = "DOC_SECTION_REFERENCES_CODE"
    FUNCTION_CALLS_FUNCTION = "FUNCTION_CALLS_FUNCTION"
    TEST_COVERS_REQUIREMENT = "TEST_COVERS_REQUIREMENT"
    TEST_COVERS_ACCEPTANCE_CRITERION = "TEST_COVERS_ACCEPTANCE_CRITERION"
    TEST_COVERS_FUNCTION = "TEST_COVERS_FUNCTION"
    TEST_COVERS_CODE = "TEST_COVERS_CODE"
    ADR_DECIDES = "ADR_DECIDES"
    KNOWN_ISSUE_AFFECTS = "KNOWN_ISSUE_AFFECTS"
    PROMPT_USED_BY = "PROMPT_USED_BY"
    CONTEXT_PACK_REFERENCES = "CONTEXT_PACK_REFERENCES"


class Node(BaseModel):
    """Base node record.

    Parsers emit nodes without `snapshot_id`, `created_at`, `last_seen_at`, `last_modified_at`;
    the indexer fills those in. `content_hash` is set by the parser when the node maps 1:1 to a
    file. `source_path` is repo-relative.
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    id: str
    node_type: NodeType
    source_path: str | None = None
    content_hash: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)

    # Filled by the indexer; left None at parse time.
    snapshot_id: str | None = None
    created_at: datetime | None = None
    last_seen_at: datetime | None = None
    last_modified_at: datetime | None = None


class Edge(BaseModel):
    """Base edge record.

    Same indexer-vs-parser split as `Node`.
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    id: str
    edge_type: EdgeType
    from_node_id: str
    to_node_id: str
    properties: dict[str, Any] = Field(default_factory=dict)

    snapshot_id: str | None = None
    created_at: datetime | None = None
    last_seen_at: datetime | None = None
    last_modified_at: datetime | None = None


class ParseResult(BaseModel):
    """Aggregate emitted by a parser for a single file."""

    model_config = ConfigDict(extra="forbid", frozen=False)

    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


ParserKind = Literal[
    "markdown",
    "feature_packet",
    "adr",
    "python_code",
    "baml",
    "test_file",
    "config",
    "known_issues",
    "context_pack",
]


def slugify_path(p: str | Path) -> str:
    """Repo-relative path → ID-safe slug. e.g., `docs/01-core/product-vision.md` → `docs:01-core:product-vision.md`."""

    return str(p).replace("\\", "/").replace("/", ":")


def slugify_heading(h: str) -> str:
    """Heading text → URL-safe anchor slug. Mirrors GitHub-flavored markdown."""

    cleaned = h.strip().lower()
    cleaned = "".join(c if c.isalnum() or c in (" ", "-") else "" for c in cleaned)
    return "-".join(cleaned.split())
