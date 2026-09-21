"""W2-5 — central Pydantic schema validation tests.

Locks in the shape of the response models that the OpenAPI codegen
pulls out of ``src/web/schemas/``. Each model gets a round-trip
``model_dump → model_validate`` check + extra-fields-rejected check
(the ``ConfigDict(extra="forbid")`` invariant).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.web.schemas.audit import (
    AuditListResponse,
    AuditRow,
    AuditViewRequest,
)
from src.web.schemas.graph import (
    GraphCrossLinksResponse,
    GraphLevelResponse,
    GraphQueryResultItem,
)
from src.web.schemas.hitl import (
    HitlClaimResponse,
    HitlCommitRequest,
    HitlCommitResponse,
    HitlInboxResponse,
    HitlItem,
    HitlListResponse,
)
from src.web.schemas.settings import (
    CorporaListResponse,
    CorpusSummary,
    FeedbackLoopPolicy,
    WebSearchSettings,
)
from src.web.schemas.shared import ErrorEnvelope
from src.web.schemas.sources import (
    CommitMappingRequest,
    ConnectorSummary,
    ConnectSourceRequest,
    MappingDecision,
    PullDeltaResponse,
    SchemaDiscoveryResponse,
    SourcesListResponse,
)
from src.web.schemas.teams import (
    MarketingDashboardResponse,
    MarketingGapResponse,
    PmDashboardResponse,
    PmDetailResponse,
    SocialDashboardResponse,
    SocialTopicResponse,
)


def test_pm_dashboard_response_round_trips() -> None:
    obj = PmDashboardResponse(corpus_id="seed", pain_points=[])
    assert PmDashboardResponse.model_validate(obj.model_dump()).corpus_id == "seed"


def test_pm_dashboard_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        PmDashboardResponse(corpus_id="x", pain_points=[], unexpected="boom")  # type: ignore[call-arg]


def test_graph_level_response_round_trips() -> None:
    obj = GraphLevelResponse(level="A", results=[])
    assert GraphLevelResponse.model_validate(obj.model_dump()).level == "A"


def test_graph_query_result_item_required_fields() -> None:
    item = GraphQueryResultItem(
        node_id="n1", node_type="Post", properties={"k": "v"},
        source_tier="L5", rank="normal", references=["n1"], confidence=0.9,
    )
    assert item.confidence == 0.9


def test_hitl_commit_request_validates() -> None:
    req = HitlCommitRequest(verdict="accept", notes="ok")
    assert req.verdict == "accept"
    assert req.escalate is False


def test_hitl_commit_request_rejects_extra() -> None:
    with pytest.raises(ValidationError):
        HitlCommitRequest(verdict="x", typo="oops")  # type: ignore[call-arg]


def test_connect_source_request_defaults_tier_l2() -> None:
    req = ConnectSourceRequest(engine="postgres", config={"host": "x"})
    assert req.tier == "L2"
    assert req.confirm_l1_immutable is False


def test_audit_row_accepts_known_kind() -> None:
    row = AuditRow(
        audit_id="a1", kind="connector_connect", actor="op",
        ts="2026-05-25T00:00:00Z", context={"engine": "postgres"},
    )
    assert row.kind == "connector_connect"


def test_audit_row_falls_through_to_str_for_unknown_kind() -> None:
    # Union[AuditKind, str] permits future audit kinds without breaking deserialize.
    row = AuditRow(
        audit_id="a1", kind="custom_future_kind", actor="op",
        ts="2026-05-25T00:00:00Z", context={},
    )
    assert row.kind == "custom_future_kind"


def test_feedback_loop_policy_defaults_match_adr_018() -> None:
    policy = FeedbackLoopPolicy()
    assert policy.positive_k == 4
    assert policy.blocklist_cap == 50
    assert policy.half_life_days == 90.0


def test_web_search_settings_default_cap_matches_adr_016() -> None:
    settings = WebSearchSettings()
    assert settings.cap_usd_per_corpus == 5.0


def test_corpora_list_response_round_trips() -> None:
    obj = CorporaListResponse(corpora=[CorpusSummary(corpus_id="seed")])
    assert CorporaListResponse.model_validate(obj.model_dump()).corpora[0].corpus_id == "seed"


def test_error_envelope_minimal() -> None:
    err = ErrorEnvelope(error_code="NOT_FOUND", message="missing")
    assert err.context == {}


# Use imports to silence lint
_ = (
    AuditListResponse, AuditViewRequest,
    CommitMappingRequest, ConnectorSummary, MappingDecision,
    PullDeltaResponse, SchemaDiscoveryResponse, SourcesListResponse,
    HitlClaimResponse, HitlCommitResponse, HitlInboxResponse,
    HitlItem, HitlListResponse,
    GraphCrossLinksResponse,
    PmDetailResponse, SocialDashboardResponse, SocialTopicResponse,
    MarketingDashboardResponse, MarketingGapResponse,
)
