"""`/api/v1/ask` — NL question -> grounded answer over the knowledge graph.

Wraps `src/retrieval/kb_agent.KBAgent`. The agent loads compact in-memory views
of the graph (~seconds on the full corpus), so it is built once per process and
reused; a lock serializes the lazy init. Handlers are sync `def` so FastAPI runs
them on the threadpool (the agent is CPU/IO bound, not async).
"""

from __future__ import annotations

import threading

from fastapi import APIRouter

from src.web.paths import data_dir
from src.web.schemas.ask import AskRequest, AskResponse

router = APIRouter()

_lock = threading.Lock()
_agent = None


def _get_agent():
    """Process-wide KBAgent singleton (lazy; ~6s first build on the full graph)."""
    global _agent  # noqa: PLW0603 — module-level cache by design
    if _agent is None:
        with _lock:
            if _agent is None:
                from src.graph.kuzu_client import KuzuGraphClient  # noqa: PLC0415
                from src.retrieval.kb_agent import KBAgent  # noqa: PLC0415
                from src.web.graph_db import shared_database  # noqa: PLC0415

                path = data_dir() / "graph" / "kuzu.db"
                client = KuzuGraphClient(db_path=path, database=shared_database())
                _agent = KBAgent(graph_path=path, graph_client=client)
    return _agent


@router.post("", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    out = _get_agent().answer(req.question)
    return AskResponse(**out)


@router.get("/health")
def ask_health() -> dict:
    """Cheap readiness probe: agent built + school/consensus view sizes."""
    a = _get_agent()
    return {"status": "ok", "schools": len(a.schools),
            "consensus_schools": len(a.fc), "clusters": len(a.clusters)}
