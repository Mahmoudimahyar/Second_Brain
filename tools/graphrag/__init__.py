"""Repo MCP context server (gate #6 per CLAUDE.md).

Indexes the SecBrain repo (docs / code / tests / feature packets) into a graph + vector store
so the coding agent has low-token retrieval before broad file reads.

NOT to be confused with the V1 product engine MCP under `src/mcp/`. See
`docs/04-architecture/system-overview.md` "Two distinct GraphRAG deployments".
"""

__version__ = "0.1.0"
