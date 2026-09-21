"""Schemas for `POST /api/v1/evidence` — full Evidence Answer Engine response."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EvidenceRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    max_sources: int = Field(default=20, ge=1, le=50)


class EvidenceItemOut(BaseModel):
    doc_id: str
    source_type: str = Field(
        description="l1_claim | l1_page | l5_post | comment | forum_consensus"
    )
    tier: str = Field(description="L1 | L5")
    snippet: str
    score: float
    url: str = ""
    school_id: str = ""


class StanceCluster(BaseModel):
    label: str
    fraction: float
    n: int
    example_ids: list[str] = Field(default_factory=list)


class EvidenceResponse(BaseModel):
    question: str

    # EAE-R1: source-typed counts
    typed_counts: dict[str, int] = Field(
        description="Number of evidence items per source_type "
                    "(l1_claim, l5_post, comment, forum_consensus, …)"
    )

    # EAE-R2: tier-weighted reliability
    most_reliable: list[EvidenceItemOut] = Field(
        description="Top L1 then top L5 items by tier-weighted score (RA-RAG)"
    )

    # EAE-R4: opinion distribution + stance clustering
    opinion_distribution: dict[str, float] = Field(
        description="Polarity fractions: {positive, neutral, negative}"
    )
    stance_clusters: list[StanceCluster] = Field(
        default_factory=list,
        description="KPA-lite stance positions (LLM-derived when available; "
                    "polarity proxy otherwise)",
    )

    # EAE-R3/R5: popular vs correct
    popular_answer: str | None = Field(
        default=None,
        description="What the forum majority says (summary)",
    )
    authoritative_answer: str | None = Field(
        default=None,
        description="What the L1 official data says (when available)",
    )
    verdict: str = Field(
        description="agrees | contradicts | no_l1_data | insufficient_evidence"
    )

    # EAE-R7: abstention
    abstain_reason: str | None = Field(
        default=None,
        description="Set when evidence is too thin to give a reliable verdict",
    )

    # EAE-R6: full source drill-down
    sources: list[EvidenceItemOut] = Field(
        description="All evidence items (doc_id + url + snippet) for drill-down"
    )

    # LLM-grounded answer
    answer: str | None = Field(
        default=None,
        description="LLM answer grounded in the evidence; null when no LLM key",
    )

    intent: str | None = None

    model_config = ConfigDict(extra="allow")  # forward-compat: extra fields from future EAE steps pass through
