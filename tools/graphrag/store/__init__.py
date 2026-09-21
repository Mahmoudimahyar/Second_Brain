"""Graph store layer for the repo MCP context server.

Defines the `GraphClient` Protocol + one concrete SQLite-backed impl (V1 minimum viable —
structural store + property indexes; vector / HNSW will be added in Phase 3.5 once the V1
product engine bake-off picks a driver that we can share).
"""

from tools.graphrag.store.client import EdgeQuery, GraphClient, NodeQuery, Snapshot
from tools.graphrag.store.sqlite_client import SQLiteGraphClient

__all__ = ["EdgeQuery", "GraphClient", "NodeQuery", "SQLiteGraphClient", "Snapshot"]
