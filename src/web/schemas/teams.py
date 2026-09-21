"""Response schemas for ``/api/v1/teams/*``."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.teams.angles import SuggestedAngle
from src.teams.marketing import ContentGap
from src.teams.pm import PainPoint
from src.teams.social import TrendingTopic


class ClusterContribution(BaseModel):
    """One contributing-cluster row for the PM detail page.

    Populated when the loader's Post→Cluster join (via ``IN_CLUSTER``
    edges) finds members among the pain point's references. Empty list
    means no cluster mapping is known yet — UI omits the section.
    """

    model_config = ConfigDict(extra="forbid")

    cluster_id: str
    label: str
    count: int


class PmDashboardResponse(BaseModel):
    """``GET /api/v1/teams/pm`` response."""

    model_config = ConfigDict(extra="forbid")

    corpus_id: str
    pain_points: list[PainPoint] = Field(default_factory=list)


class PmDetailResponse(BaseModel):
    """``GET /api/v1/teams/pm/{pain_point_id}`` response."""

    model_config = ConfigDict(extra="forbid")

    pain_point: PainPoint
    top_clusters: list[ClusterContribution] = Field(default_factory=list)
    suggested_angles: list[SuggestedAngle] = Field(default_factory=list)


class SocialDashboardResponse(BaseModel):
    """``GET /api/v1/teams/social`` response."""

    model_config = ConfigDict(extra="forbid")

    corpus_id: str
    trends: list[TrendingTopic] = Field(default_factory=list)


class SocialTopicResponse(BaseModel):
    """``GET /api/v1/teams/social/topic/{topic_id}`` response."""

    model_config = ConfigDict(extra="forbid")

    topic: TrendingTopic
    suggested_angles: list[SuggestedAngle] = Field(default_factory=list)


class MarketingDashboardResponse(BaseModel):
    """``GET /api/v1/teams/marketing`` response."""

    model_config = ConfigDict(extra="forbid")

    corpus_id: str
    gaps: list[ContentGap] = Field(default_factory=list)


class MarketingGapResponse(BaseModel):
    """``GET /api/v1/teams/marketing/gap/{gap_id}`` response."""

    model_config = ConfigDict(extra="forbid")

    gap: ContentGap
    suggested_angles: list[SuggestedAngle] = Field(default_factory=list)


__all__ = [
    "ClusterContribution",
    "MarketingDashboardResponse",
    "MarketingGapResponse",
    "PmDashboardResponse",
    "PmDetailResponse",
    "SocialDashboardResponse",
    "SocialTopicResponse",
]
