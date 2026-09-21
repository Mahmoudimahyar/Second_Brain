"""V1.5c W1-3 — load per-team inputs from the V1 graph store.

Closes gap-audit **CRITICAL-3** + **CRITICAL-5**: the prior session shipped
hand-typed ``_seed_pm_inputs()`` lists in ``src/web/routes/teams.py``
and weakened AC-4 from ``≥ 10`` to ``≥ 6`` to keep the seed test
passing. The remediation:

1. The three loader functions below query the V1 graph for the
   relevant Pass-4 / Pass-2-3 outputs and return the typed inputs each
   team aggregator expects.
2. ``src/web/routes/teams.py`` prefers the graph data; when the graph
   has no relevant nodes (fresh dev environment, no V1 ingest yet) the
   route reads from a JSON fixture (``tests/fixtures/teams_offline_seed.json``)
   so the UI still shows something.
3. The route never imports the fixture directly — the fixture-loading
   helper here does.

Pass-4 node schema (see ``src/extraction/pass4_sweep.py``):

- ``SentimentAnnotation`` — properties: ``post_id``, ``verdict``
  ("positive" / "negative" / "neutral" / "mixed"), ``confidence``,
  ``target_entities``, ``reasoning``. Connected to source post via
  ``ANNOTATES`` edge.
- ``InterviewQuestion`` — properties: ``text``, ``school_mention``,
  ``year``, ``advice_given``, ``source_post_id``.
- ``Claim`` — properties: ``subject``, ``predicate``, ``value``,
  ``cycle_year``, ``confidence``, ``source_post_id``.

Each loader translates these into the team-specific input dataclass
(``PainPointInput`` / ``TopicMention`` / ``MarketingMention``).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from src.graph.client import Node
from src.teams.marketing import MarketingMention
from src.teams.pm import PainPointInput
from src.teams.social import TopicMention

# ----------------------------------------------------------------------
# Graph access — narrow protocol so tests can pass any client
# ----------------------------------------------------------------------


class _GraphReader(Protocol):
    """Subset of GraphClient used by the loaders. Mirrors the V1.5c
    ``nodes_of_label`` API added on ``KuzuGraphClient`` in W1-3."""

    def nodes_of_label(self, label: str, *, limit: int = 10_000) -> list[Node]: ...


def _post_tier_map(graph: _GraphReader) -> dict[str, str]:
    """Build ``{post_id → source_tier}`` once per loader call so we don't
    issue an N+1 query per SentimentAnnotation. Returns an empty dict
    when the graph has no Post nodes."""

    out: dict[str, str] = {}
    for n in graph.nodes_of_label("Post"):
        tier = n.source_tier
        if tier:
            out[n.id] = tier
    return out


def _post_cluster_map(graph: _GraphReader) -> dict[str, tuple[str, str]]:
    """Build ``{post_id → (cluster_id, cluster_label)}`` from Cluster
    nodes' ``member_post_ids`` property (populated by Pass-3). When a
    post is in multiple clusters, the last one wins (Pass-3 today writes
    a single membership per post, so collisions are non-pathological).
    """

    out: dict[str, tuple[str, str]] = {}
    for n in graph.nodes_of_label("Cluster"):
        props = n.properties or {}
        label = str(props.get("topic_label") or n.id)
        members = props.get("member_post_ids") or []
        if isinstance(members, list):
            for pid in members:
                if isinstance(pid, str) and pid:
                    out[pid] = (n.id, label)
    return out


# ----------------------------------------------------------------------
# Verdict / sentiment mapping
# ----------------------------------------------------------------------


_VERDICT_TO_SENTIMENT: dict[str, float] = {
    "negative": -0.7,
    "positive": 0.7,
    "neutral": 0.0,
    "mixed": -0.1,  # mixed leans slightly negative for pain-point ranking
}


def _verdict_to_sentiment(verdict: str | None, confidence: float | None) -> float:
    """Map ``SentimentAnnotation.verdict`` + confidence → numeric sentiment."""

    base = _VERDICT_TO_SENTIMENT.get((verdict or "neutral").lower(), 0.0)
    if confidence is None:
        return base
    return base * max(0.0, min(1.0, float(confidence)))


def _audience_segment_from_post_id(post_id: str) -> str:
    """Heuristic mapping from a forum post-id namespace to an audience
    segment label."""

    pid = (post_id or "").lower()
    if "predental" in pid or "pre-dental" in pid or "applicant" in pid:
        return "applicants"
    if "dental_residency" in pid or "resident" in pid:
        return "residents"
    if "dentistry" in pid or "professional" in pid or "dentist" in pid:
        return "professionals"
    return "applicants"  # dental-applicant platform default


def _label_from_target_entities(target_entities: list[Any] | None) -> str | None:
    """Derive a topic label from the first non-empty target entity."""

    if not target_entities:
        return None
    for entity in target_entities:
        if isinstance(entity, str) and entity.strip():
            return _slugify(entity)
    return None


def _slugify(text: str) -> str:
    """Tiny slug helper — lowercase + underscores."""

    return "_".join(
        chunk for chunk in
        "".join(c.lower() if c.isalnum() else " " for c in text).split()
    )


# ----------------------------------------------------------------------
# Loaders
# ----------------------------------------------------------------------


def load_pm_inputs_from_graph(graph: _GraphReader) -> list[PainPointInput]:
    """Convert ``SentimentAnnotation`` nodes into ``PainPointInput`` rows.

    Each annotation becomes one input. The label is the slugified first
    target entity; the audience segment is heuristic from the source
    post-id; the sentiment is mapped from the verdict + confidence.
    Annotations with no target entity are skipped (no label to bucket
    them under).

    V1.5d: also pre-fetches the Post→tier and Post→cluster maps so each
    input carries ``source_tier`` + ``cluster_id`` + ``cluster_label``
    when available. Empty maps just mean the resulting PainPoints will
    have empty ``tier_mix`` + no top_clusters — honest, not synthetic.
    """

    tier_map = _post_tier_map(graph)
    cluster_map = _post_cluster_map(graph)
    nodes = graph.nodes_of_label("SentimentAnnotation")
    out: list[PainPointInput] = []
    for n in nodes:
        props = n.properties or {}
        post_id = str(props.get("post_id") or "")
        label = _label_from_target_entities(props.get("target_entities") or [])
        if not label or not post_id:
            continue
        sentiment = _verdict_to_sentiment(
            verdict=str(props.get("verdict") or ""),
            confidence=props.get("confidence"),
        )
        excerpt = str(props.get("reasoning") or "")[:280]
        ts = _parse_iso(
            props.get("ingest_iso") or props.get("t_valid_from"),
        )
        cluster_id, cluster_label = (None, None)
        if post_id in cluster_map:
            cluster_id, cluster_label = cluster_map[post_id]
        out.append(PainPointInput(
            label=label,
            audience_segment=_audience_segment_from_post_id(post_id),
            sentiment=sentiment,
            source_id=post_id,
            excerpt=excerpt,
            timestamp=ts,
            source_tier=tier_map.get(post_id),
            cluster_id=cluster_id,
            cluster_label=cluster_label,
        ))
    return out


def load_social_inputs_from_graph(graph: _GraphReader) -> list[TopicMention]:
    """Convert ``SentimentAnnotation`` nodes into ``TopicMention`` rows
    for the social trending dashboard.

    Timestamp source priority: ``properties.ingest_iso`` →
    ``properties.t_valid_from`` → now. Sentiment mapped as for PM.
    """

    now = datetime.now(UTC)
    nodes = graph.nodes_of_label("SentimentAnnotation")
    out: list[TopicMention] = []
    for n in nodes:
        props = n.properties or {}
        post_id = str(props.get("post_id") or "")
        label = _label_from_target_entities(props.get("target_entities") or [])
        if not label or not post_id:
            continue
        ts = _parse_iso(
            props.get("ingest_iso") or props.get("t_valid_from"),
        ) or now
        out.append(TopicMention(
            topic=label,
            timestamp=ts,
            source_id=post_id,
            sentiment=_verdict_to_sentiment(
                verdict=str(props.get("verdict") or ""),
                confidence=props.get("confidence"),
            ),
            excerpt=str(props.get("reasoning") or "")[:240],
        ))
    return out


def load_marketing_inputs_from_graph(graph: _GraphReader) -> list[MarketingMention]:
    """Convert ``SentimentAnnotation`` nodes into ``MarketingMention``
    rows for the marketing content-gap dashboard.

    Negative-leaning mentions surface as content gaps; the gap detector
    in ``src/teams/marketing.py`` filters by sentiment + volume.
    """

    nodes = graph.nodes_of_label("SentimentAnnotation")
    out: list[MarketingMention] = []
    for n in nodes:
        props = n.properties or {}
        post_id = str(props.get("post_id") or "")
        label = _label_from_target_entities(props.get("target_entities") or [])
        if not label or not post_id:
            continue
        out.append(MarketingMention(
            topic=label,
            sentiment=_verdict_to_sentiment(
                verdict=str(props.get("verdict") or ""),
                confidence=props.get("confidence"),
            ),
            source_id=post_id,
            excerpt=str(props.get("reasoning") or "")[:240],
        ))
    return out


# ----------------------------------------------------------------------
# Offline fixture fallback — never imported by the route directly
# ----------------------------------------------------------------------


# Resolve the fixture path relative to the repo root rather than the
# pytest CWD — the route loader is invoked from arbitrary CWDs (FastAPI
# worker, tests, CLI), and a bare ``Path("tests")`` would resolve to
# whatever the process started from. The fixture lives under
# ``tests/fixtures/`` two levels up from this file.
_OFFLINE_FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "tests"
    / "fixtures"
    / "teams_offline_seed.json"
)


def load_offline_seed(
    kind: str,
    *,
    fixture_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Load the offline-mode seed fixture for ``kind`` ∈ ``{"pm", "social", "marketing"}``.

    Used by the route handler when (a) ``SECBRAIN_OFFLINE=1`` is set or
    (b) the graph holds no ``SentimentAnnotation`` nodes (fresh dev
    environment with no V1 ingest yet) — so the dashboards still render
    something. Tests can override the path via ``fixture_path``.
    """

    path = fixture_path or _OFFLINE_FIXTURE_PATH
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if kind not in payload:
        return []
    rows = payload[kind]
    if isinstance(rows, list):
        return list(rows)
    return []


def offline_mode_enabled() -> bool:
    """True when ``SECBRAIN_OFFLINE=1``."""

    return os.environ.get("SECBRAIN_OFFLINE") == "1"


def pm_inputs_from_seed(rows: list[dict[str, Any]]) -> list[PainPointInput]:
    """V1.5d: optional ``days_ago``, ``source_tier``, ``cluster_id``,
    ``cluster_label`` fields populate the corresponding PainPointInput
    fields when present. Older fixtures without these fields still work
    — the resulting PainPoints just have empty trend / tier_mix.
    """

    now = datetime.now(UTC)
    out: list[PainPointInput] = []
    for r in rows:
        days_ago = r.get("days_ago")
        ts = None
        if days_ago is not None:
            try:
                ts = now - timedelta(days=float(days_ago))
            except (TypeError, ValueError):
                ts = None
        out.append(PainPointInput(
            label=str(r["label"]),
            audience_segment=str(r["audience_segment"]),
            sentiment=float(r["sentiment"]),
            source_id=str(r["source_id"]),
            excerpt=str(r.get("excerpt", "")),
            timestamp=ts,
            source_tier=(
                str(r["source_tier"]) if r.get("source_tier") else None
            ),
            cluster_id=(
                str(r["cluster_id"]) if r.get("cluster_id") else None
            ),
            cluster_label=(
                str(r["cluster_label"]) if r.get("cluster_label") else None
            ),
        ))
    return out


def social_mentions_from_seed(rows: list[dict[str, Any]]) -> list[TopicMention]:
    now = datetime.now(UTC)
    out: list[TopicMention] = []
    for r in rows:
        # Seed rows carry days_ago (back-dating from "now") for trend-window math.
        days_ago = float(r.get("days_ago", 0))
        out.append(TopicMention(
            topic=str(r["topic"]),
            timestamp=now - timedelta(days=days_ago),
            source_id=str(r["source_id"]),
            sentiment=float(r.get("sentiment", 0.0)),
            excerpt=str(r.get("excerpt", "")),
        ))
    return out


def marketing_mentions_from_seed(rows: list[dict[str, Any]]) -> list[MarketingMention]:
    return [
        MarketingMention(
            topic=str(r["topic"]),
            sentiment=float(r["sentiment"]),
            source_id=str(r["source_id"]),
            excerpt=str(r.get("excerpt", "")),
        )
        for r in rows
    ]


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


__all__ = [
    "load_marketing_inputs_from_graph",
    "load_offline_seed",
    "load_pm_inputs_from_graph",
    "load_social_inputs_from_graph",
    "marketing_mentions_from_seed",
    "offline_mode_enabled",
    "pm_inputs_from_seed",
    "social_mentions_from_seed",
]
