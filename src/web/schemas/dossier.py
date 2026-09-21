"""Request schema for the Evidence Dossier endpoint (ED-8)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DossierRequest(BaseModel):
    question: str = Field(..., min_length=2, description="Natural-language question")
    display_k: int = Field(25, ge=1, le=100, description="Max drill-down sources to return")
