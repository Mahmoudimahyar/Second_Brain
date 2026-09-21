"""`POST /api/v1/dossier` — the Evidence Dossier Engine (ED-3 … ED-8).

Returns an adjudicated evidence dossier for a natural-language question: typed
evidence counts, most-reliable official sources (L1 facts + article prose), a counted
opinion distribution, a popular-vs-correct verdict, drill-down sources, and calibrated
abstention.

Backed by the bundle artifacts (parquet graph, embeddings, documents.sqlite,
reddit_school_link.sqlite, L1 article index) under `$SECBRAIN_BUNDLE`. One shared
engine is lazily built on first request. The LLM is constructed via the vendor-locked
gateway (no SDK import here).
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException

from src.web.schemas.dossier import DossierRequest

router = APIRouter()

_engine = None


def _build_llm():
    """Benchmark-won bulk model via the gateway (vendor-lock honoured)."""
    try:
        from src.gateway.openai_adapter import OpenAIAdapter  # noqa: PLC0415

        return OpenAIAdapter(
            vendor="together", model="openai/gpt-oss-20b",
            api_key_env="TOGETHER_API_KEY", base_url="https://api.together.xyz/v1",
            pricing_per_million_tokens_in=0.05, pricing_per_million_tokens_out=0.20,
            timeout=60, max_retries=2,
        )
    except Exception:  # noqa: BLE001 — degrade to facts-only (no stance/verdict LLM)
        return None


def _get_engine():
    global _engine  # noqa: PLW0603 — process-wide singleton
    if _engine is None:
        bundle = os.environ.get("SECBRAIN_BUNDLE")
        if not bundle or not os.path.isdir(bundle):
            raise HTTPException(
                status_code=503,
                detail="SECBRAIN_BUNDLE not configured (path to the corpus bundle dir)",
            )
        from src.retrieval.dossier import EvidenceDossierEngine  # noqa: PLC0415

        _engine = EvidenceDossierEngine(bundle, llm=_build_llm())
    return _engine


@router.post("")
def dossier(req: DossierRequest) -> dict:
    """Full adjudicated evidence dossier for a natural-language question."""
    return _get_engine().answer(req.question, display_k=req.display_k)


@router.get("/sources")
def dossier_sources(stat_id: str | None = None, school: str | None = None,
                    label: str = "positive", offset: int = 0, limit: int = 50) -> dict:
    """Drill-down: the exact source posts/comments behind a statistic (paginated,
    hydrated to url + snippet). Pass `stat_id` from a statistic's `drill_down` field, or
    (`school`, `label`) from a ranking row's drill-down."""
    return _get_engine().sources(
        stat_id, school=school, label=label,
        offset=max(0, offset), limit=min(max(1, limit), 200))


@router.get("/health")
def dossier_health() -> dict:
    """Readiness probe: reports whether the bundle is configured + loaded."""
    bundle = os.environ.get("SECBRAIN_BUNDLE")
    configured = bool(bundle and os.path.isdir(bundle))
    return {
        "status": "ok" if configured else "unconfigured",
        "bundle": bundle,
        "loaded": _engine is not None,
    }
