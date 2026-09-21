"""V1 retrieval surface (MCP inbound + Python API). Per FR-8.

Lazy re-export (PEP 562): importing a leaf module (e.g. `src.retrieval.stance` or
`src.retrieval.dossier`) must NOT eagerly drag in `src.retrieval.api` and its heavy
graph / gateway / conflict chain (kuzu, the LLM SDKs, pydantic, sklearn). The public API
names stay importable — `from src.retrieval import RetrievalService` — resolved on first
access. This keeps lean consumers (the offline no-key pack) from pulling the whole engine.
"""

__all__ = ["CanonicalEntity", "QueryResult", "RetrievalService"]


def __getattr__(name):  # PEP 562
    if name in __all__:
        from src.retrieval.api import CanonicalEntity, QueryResult, RetrievalService
        return {"CanonicalEntity": CanonicalEntity, "QueryResult": QueryResult,
                "RetrievalService": RetrievalService}[name]
    raise AttributeError(f"module 'src.retrieval' has no attribute {name!r}")
