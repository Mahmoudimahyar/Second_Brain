"""`POST /api/v1/evidence` — full Evidence Answer Engine (EAE) over the graph.

Runs all 7 EAE steps:
  R1 typed source counts   R2 tier-weighted reliability   R3 popular-vs-correct
  R4 stance clustering     R5 verdict                     R6 source drill-down
  R7 comment recall (FTS5 on documents.sqlite, LIKE fallback)

Shares the process-wide KBAgent singleton from `src.web.routes.ask`.
"""

from __future__ import annotations

from fastapi import APIRouter

from src.web.routes.ask import _get_agent
from src.web.schemas.evidence import EvidenceRequest, EvidenceResponse

router = APIRouter()


@router.post("", response_model=EvidenceResponse)
def evidence(req: EvidenceRequest) -> EvidenceResponse:
    """Full 7-step Evidence Answer Engine response for a natural-language question."""
    agent = _get_agent()
    out = agent.evidence_answer(req.question)
    # Truncate sources to requested limit
    out["sources"] = out.get("sources", [])[:req.max_sources]
    return EvidenceResponse(**out)


@router.get("/health")
def evidence_health() -> dict:
    """Readiness probe: reports corpus size + FTS5 availability."""
    a = _get_agent()
    return {
        "status": "ok",
        "schools": len(a.schools),
        "consensus_schools": len(a.fc),
        "fts5_available": a._check_fts5(),  # noqa: SLF001
        "documents_db": str(a._docs_db_path) if a._docs_db_path else None,  # noqa: SLF001
    }
