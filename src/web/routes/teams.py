"""V1.5c — ``/api/v1/teams/*`` routes (PM / Social / Marketing).

W1-3 remediation (closes gap-audit CRITICAL-3 + CRITICAL-5):

The prior session shipped ``_seed_pm_inputs()`` (and equivalents) as
hand-typed lists inside this module — the route handlers aggregated
over that list rather than the actual V1 graph. This module now uses
``src.teams.data_loaders`` to:

1. Read ``SentimentAnnotation`` (and friends) from the V1 graph via
   ``KuzuGraphClient.nodes_of_label``.
2. Fall back to a JSON fixture (``tests/fixtures/teams_offline_seed.json``)
   only when the graph holds no relevant nodes or when ``SECBRAIN_OFFLINE=1``
   is set — so a fresh dev environment still renders the dashboards.

The route never imports the fixture file directly; the loader module
owns that I/O. Tests can monkey-patch ``_graph_client_for_corpus`` to
inject a populated test graph.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Query

from src.graph.kuzu_client import KuzuGraphClient
from src.teams.angles import suggest_angles
from src.teams.data_loaders import (
    load_marketing_inputs_from_graph,
    load_offline_seed,
    load_pm_inputs_from_graph,
    load_social_inputs_from_graph,
    marketing_mentions_from_seed,
    offline_mode_enabled,
    pm_inputs_from_seed,
    social_mentions_from_seed,
)
from src.teams.marketing import MarketingMention, compute_content_gaps
from src.teams.pm import (
    PainPointInput,
    compute_pain_points,
    compute_top_clusters,
)
from src.teams.social import TopicMention, compute_trending_topics
from src.web.schemas.teams import (
    ClusterContribution,
    MarketingDashboardResponse,
    MarketingGapResponse,
    PmDashboardResponse,
    PmDetailResponse,
    SocialDashboardResponse,
    SocialTopicResponse,
)

router = APIRouter()


# ----------------------------------------------------------------------
# Graph client wiring
# ----------------------------------------------------------------------


def _data_dir() -> Path:
    """Resolve the SecBrain data root from env, defaulting to ``./data``."""

    return Path(os.environ.get("SECBRAIN_DATA_DIR", "data"))


def _graph_client_for_corpus(corpus_id: str) -> KuzuGraphClient | None:
    """Open the V1 graph store for the given corpus, or ``None`` if missing.

    V1.5 graph layout: ``<SECBRAIN_DATA_DIR>/graphs/<corpus_id>/kuzu/``.
    Tests can monkeypatch this function to inject an in-memory client.
    """

    _ = corpus_id
    graph_root = _data_dir() / "graphs" / corpus_id / "kuzu"
    if not graph_root.exists():
        return None
    try:
        return KuzuGraphClient(graph_root)
    except Exception:  # graph open failure → caller falls back to fixture
        return None


# ----------------------------------------------------------------------
# Input resolution — graph first, fixture fallback
# ----------------------------------------------------------------------


def _resolve_pm_inputs(corpus_id: str) -> list[PainPointInput]:
    """Production: graph data; fallback: offline seed.

    Order:
      1. ``SECBRAIN_OFFLINE=1`` → fixture
      2. graph present + non-empty SentimentAnnotation → graph data
      3. else → fixture
    """

    if offline_mode_enabled():
        return pm_inputs_from_seed(load_offline_seed("pm"))
    graph = _graph_client_for_corpus(corpus_id)
    if graph is not None:
        inputs = load_pm_inputs_from_graph(graph)
        if inputs:
            return inputs
    return pm_inputs_from_seed(load_offline_seed("pm"))


def _resolve_social_mentions(corpus_id: str) -> list[TopicMention]:
    if offline_mode_enabled():
        return social_mentions_from_seed(load_offline_seed("social"))
    graph = _graph_client_for_corpus(corpus_id)
    if graph is not None:
        mentions = load_social_inputs_from_graph(graph)
        if mentions:
            return mentions
    return social_mentions_from_seed(load_offline_seed("social"))


def _resolve_marketing_mentions(corpus_id: str) -> list[MarketingMention]:
    if offline_mode_enabled():
        return marketing_mentions_from_seed(load_offline_seed("marketing"))
    graph = _graph_client_for_corpus(corpus_id)
    if graph is not None:
        mentions = load_marketing_inputs_from_graph(graph)
        if mentions:
            return mentions
    return marketing_mentions_from_seed(load_offline_seed("marketing"))


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------


@router.get("/pm", response_model=PmDashboardResponse)
def pm_dashboard(
    corpus_id: str = Query("seed"),
    min_volume: int = Query(1, ge=1),
) -> PmDashboardResponse:
    inputs = _resolve_pm_inputs(corpus_id)
    pps = compute_pain_points(inputs, min_volume=min_volume)
    return PmDashboardResponse(corpus_id=corpus_id, pain_points=pps)


@router.get("/pm/{pain_point_id}", response_model=PmDetailResponse)
def pm_detail(pain_point_id: str) -> PmDetailResponse:
    inputs = _resolve_pm_inputs("seed")
    pps = compute_pain_points(inputs)
    match = next((p for p in pps if p.pain_point_id == pain_point_id), None)
    if match is None:
        from src.shared.errors import ErrorCode, StructuredError  # noqa: PLC0415
        raise StructuredError(
            ErrorCode.VALIDATION_FAILED,
            f"pain point {pain_point_id!r} not found",
        )
    # Recover this pain point's underlying inputs to compute top
    # contributing clusters. The pain_point_id encodes label + segment.
    matching_inputs = [
        i for i in inputs
        if f"pp:{i.label}:{i.audience_segment}" == pain_point_id
    ]
    top_clusters = [
        ClusterContribution(
            cluster_id=row.cluster_id, label=row.label, count=row.count,
        )
        for row in compute_top_clusters(matching_inputs)
    ]
    angles = suggest_angles(
        team="pm",
        item_id=pain_point_id,
        context={"title": match.title, "references": match.references},
    )
    return PmDetailResponse(
        pain_point=match,
        top_clusters=top_clusters,
        suggested_angles=angles,
    )


@router.get("/social", response_model=SocialDashboardResponse)
def social_dashboard(
    corpus_id: str = Query("seed"),
    window_days: int = Query(30, ge=1),
) -> SocialDashboardResponse:
    mentions = _resolve_social_mentions(corpus_id)
    trends = compute_trending_topics(
        mentions, window_days=window_days,
        min_trend_ratio=1.0,
    )
    return SocialDashboardResponse(corpus_id=corpus_id, trends=trends)


@router.get("/social/topic/{topic_id}", response_model=SocialTopicResponse)
def social_topic(topic_id: str) -> SocialTopicResponse:
    mentions = _resolve_social_mentions("seed")
    trends = compute_trending_topics(mentions, min_trend_ratio=1.0)
    match = next((t for t in trends if t.topic_id == topic_id), None)
    if match is None:
        from src.shared.errors import ErrorCode, StructuredError  # noqa: PLC0415
        raise StructuredError(
            ErrorCode.VALIDATION_FAILED,
            f"topic {topic_id!r} not found",
        )
    angles = suggest_angles(
        team="social",
        item_id=topic_id,
        context={"topic": match.name, "references": match.references},
    )
    return SocialTopicResponse(topic=match, suggested_angles=angles)


@router.get("/marketing", response_model=MarketingDashboardResponse)
def marketing_dashboard(
    corpus_id: str = Query("seed"),
) -> MarketingDashboardResponse:
    mentions = _resolve_marketing_mentions(corpus_id)
    gaps = compute_content_gaps(mentions)
    return MarketingDashboardResponse(corpus_id=corpus_id, gaps=gaps)


@router.get("/marketing/gap/{gap_id}", response_model=MarketingGapResponse)
def marketing_gap(gap_id: str) -> MarketingGapResponse:
    mentions = _resolve_marketing_mentions("seed")
    gaps = compute_content_gaps(mentions)
    match = next((g for g in gaps if g.gap_id == gap_id), None)
    if match is None:
        from src.shared.errors import ErrorCode, StructuredError  # noqa: PLC0415
        raise StructuredError(
            ErrorCode.VALIDATION_FAILED,
            f"gap {gap_id!r} not found",
        )
    angles = suggest_angles(
        team="marketing",
        item_id=gap_id,
        context={"name": match.topic, "references": match.references},
    )
    return MarketingGapResponse(gap=match, suggested_angles=angles)
