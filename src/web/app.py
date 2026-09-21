"""V1.5b FastAPI factory.

Builds the FastAPI app, mounts `/api/v1/*` routers, applies middleware,
and registers exception handlers. Localhost-only binding (V1.5).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.shared.errors import StructuredError
from src.web.middleware.audit_ui import UIAuditMiddleware
from src.web.paths import sqlite_path  # re-exported for back-compat
from src.web.routes import (
    ask, audit, dossier, evidence, graph, hitl, settings, sources, teams, website_crawl,
)

log = structlog.get_logger(__name__)

__all__ = ["create_app", "sqlite_path"]


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown hook for the FastAPI app."""

    log.info("web.start", sqlite_path=str(sqlite_path()))
    yield
    log.info("web.stop")


def create_app() -> FastAPI:
    # Parity with the CLI callback: vendor keys + SECBRAIN_* knobs come from .env
    # (uvicorn doesn't load it; without this /api/v1/ask degrades to facts-only).
    from pathlib import Path  # noqa: PLC0415

    from src.shared.env_loader import load_dotenv  # noqa: PLC0415

    load_dotenv(Path(".env"))

    app = FastAPI(
        title="SecBrain V1.5b",
        version="1.5.0",
        description=(
            "V1.5 web layer — Pydantic-driven contracts over the V1 + V1.5a "
            "engines. Localhost-only (no auth, V1.5)."
        ),
        lifespan=_lifespan,
    )

    # V1.5 = localhost only; CORS off by default. V2 multi-tenant will
    # enable controlled cross-origin access.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    # W2-4 — record one `ui_*` audit row per `/api/v1/*` request (closes
    # V1.5b NFR-8 / FR-1.5b-8.3 / gap-audit MED-5).
    app.add_middleware(UIAuditMiddleware)

    app.include_router(sources.router, prefix="/api/v1/sources", tags=["sources"])
    app.include_router(ask.router, prefix="/api/v1/ask", tags=["ask"])
    # EAE-4: full Evidence Answer Engine
    app.include_router(evidence.router, prefix="/api/v1/evidence", tags=["evidence"])
    # ED-8: Evidence Dossier Engine (bundle-backed; counted stance + L1-anchored verdict)
    app.include_router(dossier.router, prefix="/api/v1/dossier", tags=["dossier"])
    app.include_router(graph.router, prefix="/api/v1/graph", tags=["graph"])
    app.include_router(hitl.router, prefix="/api/v1/hitl", tags=["hitl"])
    app.include_router(settings.router, prefix="/api/v1/settings", tags=["settings"])
    app.include_router(audit.router, prefix="/api/v1/audit", tags=["audit"])
    app.include_router(teams.router, prefix="/api/v1/teams", tags=["teams"])
    # V1.6a — website-crawl ingestion under /api/v1/ingest/web/*
    app.include_router(
        website_crawl.router,
        prefix="/api/v1/ingest/web",
        tags=["website_crawl"],
    )

    @app.exception_handler(StructuredError)
    async def _structured_error_handler(
        request: Request, exc: StructuredError,
    ) -> JSONResponse:
        log.warning(
            "web.structured_error",
            path=request.url.path,
            error_code=exc.error_code.value,
            message=exc.message,
        )
        # Map structured-error codes to appropriate HTTP statuses.
        status = _status_for(exc)
        return JSONResponse(
            status_code=status, content=exc.to_dict(),
        )

    @app.get("/api/v1/health")
    async def _health() -> dict[str, str]:
        return {"status": "ok", "version": "1.5.0"}

    return app


def _status_for(exc: StructuredError) -> int:
    """Map structured-error codes to HTTP statuses."""

    not_found = {"CONNECTOR_NOT_FOUND", "SCHEMA_NOT_DISCOVERED"}
    conflict = {"L1_IMMUTABLE_REJECT", "CONNECTOR_ALREADY_REGISTERED",
                "CRAWL_RUNNING"}
    bad_request = {
        "VALIDATION_FAILED", "INGESTION_PAYLOAD_MISSING",
        "INGESTION_MANIFEST_INVALID", "INVALID_MAPPING",
        "MAPPING_NOT_COMMITTED", "ENGINE_UNSUPPORTED",
        "SCHEMA_TOO_LARGE", "CRED_NOT_FOUND",
    }
    # V1.6a maps DOMAIN_BLOCKED / UNREACHABLE / INVALID_CRON / L1_NOT_CONFIRMED
    # to 422 (unprocessable entity) per api.md.
    unprocessable = {
        "DOMAIN_BLOCKED", "UNREACHABLE_DOMAIN", "INVALID_CRON",
        "L1_NOT_CONFIRMED",
    }
    too_many = {"BUDGET_EXCEEDED"}
    service_unavailable = {"SCRAPINGBEE_UNAVAILABLE"}
    code = exc.error_code.value
    if code in not_found:
        return 404
    if code in conflict:
        return 409
    if code in unprocessable:
        return 422
    if code in too_many:
        return 429
    if code in service_unavailable:
        return 503
    if code in bad_request:
        return 400
    return 500
