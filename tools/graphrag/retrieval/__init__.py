"""Retrieval primitives for the repo MCP context server.

One module per tool from `tools/mcp/tools.md`. Each primitive is a pure function taking a
`GraphClient`/`SQLiteGraphClient` and the tool's input shape, returning a Pydantic result. The
MCP server (Phase 5) wraps them with the stdio protocol.
"""

from tools.graphrag.retrieval.create_task_brief import create_task_brief
from tools.graphrag.retrieval.explain_feature import explain_feature
from tools.graphrag.retrieval.find_stale_docs import find_stale_docs
from tools.graphrag.retrieval.find_symbol import find_symbol
from tools.graphrag.retrieval.get_code_for_doc import get_code_for_doc
from tools.graphrag.retrieval.get_docs_for_code import get_docs_for_code
from tools.graphrag.retrieval.get_feature_packet import get_feature_packet
from tools.graphrag.retrieval.get_related_tests import get_related_tests
from tools.graphrag.retrieval.plan_change import plan_change
from tools.graphrag.retrieval.search_codebase import search_codebase
from tools.graphrag.retrieval.validate_feature_packet import validate_feature_packet

__all__ = [
    "create_task_brief",
    "explain_feature",
    "find_stale_docs",
    "find_symbol",
    "get_code_for_doc",
    "get_docs_for_code",
    "get_feature_packet",
    "get_related_tests",
    "plan_change",
    "search_codebase",
    "validate_feature_packet",
]
