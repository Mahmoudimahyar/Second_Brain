"""W1-3 — tests for ``src/teams/data_loaders.py``.

Covers:
- ``load_pm_inputs_from_graph`` translates ``SentimentAnnotation`` nodes
  into ``PainPointInput`` rows with label / audience_segment / sentiment.
- ``load_social_inputs_from_graph`` produces ``TopicMention`` rows.
- ``load_marketing_inputs_from_graph`` produces ``MarketingMention`` rows.
- Offline-fixture loading returns the right shape per ``kind``.
- All inputs carry the source post-id back-reference for the
  citation-traceability NFR-1.5c-4 invariant.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.graph.client import Node
from src.teams.data_loaders import (
    load_marketing_inputs_from_graph,
    load_offline_seed,
    load_pm_inputs_from_graph,
    load_social_inputs_from_graph,
    marketing_mentions_from_seed,
    pm_inputs_from_seed,
    social_mentions_from_seed,
)

# ----------------------------------------------------------------------
# Stub graph that holds nodes_of_label callable
# ----------------------------------------------------------------------


@dataclass
class _StubGraph:
    by_label: dict[str, list[Node]]

    def nodes_of_label(self, label: str, *, limit: int = 10_000) -> list[Node]:
        return list(self.by_label.get(label, [])[:limit])


def _sentiment_node(
    *,
    post_id: str,
    target: str,
    verdict: str = "negative",
    confidence: float = 0.9,
    reasoning: str = "Some reasoning",
) -> Node:
    return Node(
        id=f"sentiment:{post_id}",
        label="SentimentAnnotation",
        source_tier="L5",
        properties={
            "post_id": post_id,
            "verdict": verdict,
            "confidence": confidence,
            "target_entities": [target],
            "reasoning": reasoning,
        },
    )


# ----------------------------------------------------------------------
# PM loader
# ----------------------------------------------------------------------


def test_pm_loader_returns_inputs_from_graph() -> None:
    graph = _StubGraph(by_label={
        "SentimentAnnotation": [
            _sentiment_node(post_id="post:predental:001", target="Tuition Anxiety",
                            verdict="negative", confidence=0.85),
            _sentiment_node(post_id="post:predental:002", target="Tuition Anxiety",
                            verdict="negative", confidence=0.80),
            _sentiment_node(post_id="post:predental:003", target="DAT Prep",
                            verdict="negative", confidence=0.70),
        ],
    })

    inputs = load_pm_inputs_from_graph(graph)

    assert len(inputs) == 3
    labels = sorted({i.label for i in inputs})
    assert labels == ["dat_prep", "tuition_anxiety"]
    # Every input has a real source_id (NFR-1.5c-4 traceability).
    assert all(i.source_id.startswith("post:") for i in inputs)
    # Sentiment is negative — verdict "negative" + confidence > 0 = negative.
    assert all(i.sentiment < 0 for i in inputs)


def test_pm_loader_skips_annotations_with_no_target_entity() -> None:
    graph = _StubGraph(by_label={
        "SentimentAnnotation": [
            _sentiment_node(post_id="post:1", target=""),
            Node(
                id="sentiment:post:2",
                label="SentimentAnnotation",
                source_tier="L5",
                properties={
                    "post_id": "post:2",
                    "verdict": "negative",
                    "confidence": 0.7,
                    "target_entities": [],
                    "reasoning": "no target",
                },
            ),
        ],
    })

    assert load_pm_inputs_from_graph(graph) == []


def test_pm_loader_maps_verdict_correctly() -> None:
    graph = _StubGraph(by_label={
        "SentimentAnnotation": [
            _sentiment_node(post_id="post:1", target="X", verdict="negative", confidence=1.0),
            _sentiment_node(post_id="post:2", target="X", verdict="positive", confidence=1.0),
            _sentiment_node(post_id="post:3", target="X", verdict="neutral", confidence=1.0),
            _sentiment_node(post_id="post:4", target="X", verdict="mixed", confidence=1.0),
        ],
    })

    inputs = load_pm_inputs_from_graph(graph)
    sentiments = {i.source_id: i.sentiment for i in inputs}
    assert sentiments["post:1"] < 0   # negative
    assert sentiments["post:2"] > 0   # positive
    assert sentiments["post:3"] == 0.0  # neutral
    assert sentiments["post:4"] < 0   # mixed leans slightly negative


def test_pm_loader_audience_segment_routing() -> None:
    graph = _StubGraph(by_label={
        "SentimentAnnotation": [
            _sentiment_node(post_id="post:predental:1", target="X"),
            _sentiment_node(post_id="post:dental_residency:2", target="X"),
            _sentiment_node(post_id="post:dentistry:3", target="X"),
            _sentiment_node(post_id="post:unknown:4", target="X"),
        ],
    })

    inputs = load_pm_inputs_from_graph(graph)
    seg = {i.source_id: i.audience_segment for i in inputs}
    assert seg["post:predental:1"] == "applicants"
    assert seg["post:dental_residency:2"] == "residents"
    assert seg["post:dentistry:3"] == "professionals"
    assert seg["post:unknown:4"] == "applicants"  # default


# ----------------------------------------------------------------------
# Social loader
# ----------------------------------------------------------------------


def test_social_loader_returns_topic_mentions() -> None:
    graph = _StubGraph(by_label={
        "SentimentAnnotation": [
            _sentiment_node(post_id="post:1", target="Tuition Anxiety"),
            _sentiment_node(post_id="post:2", target="Interview Logistics"),
        ],
    })

    mentions = load_social_inputs_from_graph(graph)

    assert len(mentions) == 2
    topics = sorted({m.topic for m in mentions})
    assert topics == ["interview_logistics", "tuition_anxiety"]
    assert all(m.timestamp is not None for m in mentions)


# ----------------------------------------------------------------------
# Marketing loader
# ----------------------------------------------------------------------


def test_marketing_loader_returns_mentions() -> None:
    graph = _StubGraph(by_label={
        "SentimentAnnotation": [
            _sentiment_node(post_id="post:1", target="Tuition Transparency",
                            verdict="negative"),
            _sentiment_node(post_id="post:2", target="Tuition Transparency",
                            verdict="negative"),
        ],
    })

    mentions = load_marketing_inputs_from_graph(graph)
    assert len(mentions) == 2
    assert all(m.topic == "tuition_transparency" for m in mentions)
    assert all(m.sentiment < 0 for m in mentions)


# ----------------------------------------------------------------------
# Offline fixture
# ----------------------------------------------------------------------


def test_offline_seed_pm_has_at_least_10_distinct_labels() -> None:
    """W1-4 — the offline fixture must support the restored AC-4 ≥10
    pain-points gate. With 1+ mention per label, 10+ labels → 10+ pain
    points after aggregation.
    """

    rows = load_offline_seed("pm")
    labels = {r["label"] for r in rows}
    assert len(labels) >= 10, (
        f"offline fixture should support AC-4 ≥ 10 pain points; "
        f"got {len(labels)} distinct labels"
    )


def test_pm_inputs_from_seed_round_trips() -> None:
    rows = load_offline_seed("pm")
    inputs = pm_inputs_from_seed(rows)
    assert len(inputs) == len(rows)
    assert all(i.source_id for i in inputs)


def test_social_mentions_from_seed_assigns_timestamps() -> None:
    rows = load_offline_seed("social")
    mentions = social_mentions_from_seed(rows)
    assert len(mentions) == len(rows)
    assert all(m.timestamp is not None for m in mentions)


def test_marketing_mentions_from_seed_round_trips() -> None:
    rows = load_offline_seed("marketing")
    mentions = marketing_mentions_from_seed(rows)
    assert len(mentions) == len(rows)


def test_load_offline_seed_missing_kind_returns_empty() -> None:
    assert load_offline_seed("nonexistent") == []


# ----------------------------------------------------------------------
# End-to-end: real-graph data → compute_pain_points produces 10+ pain points
# ----------------------------------------------------------------------


def test_e2e_graph_data_produces_at_least_ten_pain_points() -> None:
    """Simulate a real V1 graph populated with Pass-4 SentimentAnnotation
    output across 10+ topics, then assert ``compute_pain_points`` returns
    ≥ 10 ranked pain points. This is the production code path AC-4 covers.
    """

    from src.teams.pm import compute_pain_points  # noqa: PLC0415

    rows = load_offline_seed("pm")
    # Convert fixture rows into SentimentAnnotation nodes — simulating
    # what a Pass-4 sweep would write into the V1 graph.
    nodes: list[Node] = [
        Node(
            id=f"sentiment:{r['source_id']}",
            label="SentimentAnnotation",
            source_tier="L5",
            properties={
                "post_id": r["source_id"],
                "verdict": "negative" if r["sentiment"] < 0 else "positive",
                "confidence": min(1.0, abs(r["sentiment"]) + 0.1),
                "target_entities": [r["label"]],
                "reasoning": r.get("excerpt", ""),
            },
        )
        for r in rows
    ]
    graph = _StubGraph(by_label={"SentimentAnnotation": nodes})
    inputs = load_pm_inputs_from_graph(graph)
    pain_points = compute_pain_points(inputs, min_volume=1)
    assert len(pain_points) >= 10, (
        f"graph-fed loader should produce ≥ 10 pain points; got {len(pain_points)}"
    )


_ = pytest  # silence unused-import warning
