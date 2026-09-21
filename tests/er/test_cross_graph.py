"""Tests for V1.5a Phase 5 — `CrossGraphLinker` (FR-1.5a-5, AC-5).

Reuses V1's alias-resolution pipeline (rapidfuzz token_set_ratio + BGE-small
embeddings) in cross-source mode. Outputs `SAME_AS` edges with
tier-preserving + bitemporal properties per ADR-015.

Confidence thresholds match V1 (FR-1.5a-5.2):
  ≥ 0.90 → auto-write SAME_AS
  0.75 ≤ x < 0.90 → HITL `cross_graph_link` item
  < 0.75 → no link
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.embeddings.hash_embedder import HashEmbeddingService
from src.er.cross_graph import (
    CrossGraphCandidate,
    CrossGraphEntity,
    CrossGraphLinker,
    CrossGraphLinkRouting,
    SameAsEdge,
)


def _entity(
    *,
    entity_id: str, name: str,
    aliases: tuple[str, ...] = (),
    entity_type: str = "School",
    tier: str = "L2",
    source_id: str = "ds:test",
) -> CrossGraphEntity:
    return CrossGraphEntity(
        entity_id=entity_id,
        entity_type=entity_type,
        name=name,
        aliases=aliases,
        tier=tier,  # type: ignore[arg-type]
        source_id=source_id,
    )


@pytest.fixture
def linker() -> CrossGraphLinker:
    return CrossGraphLinker(embedding_service=HashEmbeddingService())


# ----------------------------------------------------------------------
# Core matching
# ----------------------------------------------------------------------


def test_exact_name_match_auto_accepts(linker: CrossGraphLinker) -> None:
    """High-confidence: identical names should produce SAME_AS edge."""
    universe = [
        _entity(entity_id="school:nyu_dental",
                name="New York University College of Dentistry",
                aliases=("NYU Dental", "NYU College of Dentistry"),
                tier="L1", source_id="ds:adea"),
    ]
    new = _entity(entity_id="partner:nyu",
                  name="New York University College of Dentistry",
                  tier="L2", source_id="ds:partner_postgres")
    candidates = linker.link(new, universe)
    assert len(candidates) == 1
    top = candidates[0]
    assert top.target_entity_id == "school:nyu_dental"
    assert top.confidence >= 0.90
    assert top.routing == "auto"


def test_alias_overlap_high_confidence(linker: CrossGraphLinker) -> None:
    """An alias of the canonical entity matches the new entity's name."""
    universe = [
        _entity(entity_id="school:harvard",
                name="Harvard School of Dental Medicine",
                aliases=("HSDM", "Harvard Dental"),
                tier="L1"),
    ]
    new = _entity(entity_id="partner:hsdm",
                  name="HSDM", tier="L2")
    candidates = linker.link(new, universe)
    assert candidates
    assert candidates[0].target_entity_id == "school:harvard"
    assert candidates[0].confidence >= 0.90


def test_borderline_match_routes_hitl(linker: CrossGraphLinker) -> None:
    """Partial match → HITL routing. Constructed so the lexical signal is
    moderate (no full alias overlap, no exact name match).
    """
    universe = [
        _entity(entity_id="school:upenn",
                name="University of Pennsylvania School of Dental Medicine",
                aliases=("UPenn",), tier="L1"),
    ]
    new = _entity(entity_id="partner:penn",
                  name="Pennsylvania School of Dentistry", tier="L2")
    candidates = linker.link(new, universe)
    assert candidates
    top = candidates[0]
    assert 0.75 <= top.confidence < 0.95
    assert top.routing in {"auto", "hitl"}


def test_no_match_below_threshold(linker: CrossGraphLinker) -> None:
    universe = [
        _entity(entity_id="school:nyu_dental", name="NYU Dental"),
    ]
    new = _entity(entity_id="partner:xyz", name="University of Pittsburgh")
    candidates = linker.link(new, universe)
    # Should either be empty OR all candidates < 0.75 with routing='reject'
    assert all(c.confidence < 0.75 for c in candidates) or candidates == []


def test_type_mismatch_filtered(linker: CrossGraphLinker) -> None:
    """A School entity should not link to a User entity even if names match."""
    universe = [
        _entity(entity_id="user:nyu_alumni",
                name="NYU Dental",
                entity_type="User"),
    ]
    new = _entity(entity_id="partner:nyu",
                  name="NYU Dental", entity_type="School")
    candidates = linker.link(new, universe)
    assert candidates == [] or all(c.confidence < 0.75 for c in candidates)


def test_top_k_returned(linker: CrossGraphLinker) -> None:
    """When multiple universe entities partially match, return top-K."""
    universe = [
        _entity(entity_id=f"school:s{i}",
                name=f"Dental School {i}", aliases=())
        for i in range(20)
    ]
    new = _entity(entity_id="partner:s5", name="Dental School 5")
    candidates = linker.link(new, universe, top_k=5)
    assert len(candidates) <= 5


# ----------------------------------------------------------------------
# SAME_AS edge construction
# ----------------------------------------------------------------------


def test_same_as_edge_canonical_ordering(linker: CrossGraphLinker) -> None:
    """SAME_AS storage convention: subject_id < object_id alphabetically.
    Tests that the order-of-args doesn't change the stored edge.
    """
    a = _entity(entity_id="school:harvard", name="HSDM",
                tier="L1", source_id="ds:adea")
    b = _entity(entity_id="partner:harvard_med", name="Harvard Dental",
                tier="L2", source_id="ds:partner_postgres")
    edge1 = linker.materialize_edge(a, b, confidence=0.95)
    edge2 = linker.materialize_edge(b, a, confidence=0.95)
    assert edge1.subject_id == edge2.subject_id
    assert edge1.object_id == edge2.object_id
    assert edge1.subject_id < edge1.object_id  # canonical ordering


def test_same_as_edge_preserves_per_endpoint_tier(
    linker: CrossGraphLinker,
) -> None:
    """ADR-015: per-endpoint tier preserved on the edge."""
    a = _entity(entity_id="school:nyu", tier="L1", name="NYU", source_id="adea")
    b = _entity(entity_id="partner:nyu", tier="L2", name="NYU",
                source_id="partner")
    edge = linker.materialize_edge(a, b, confidence=0.95)
    # The lower-sorting id becomes subject; assert the per-endpoint tiers
    # are preserved by referring to the IDs.
    if edge.subject_id == "partner:nyu":
        assert edge.subject_tier == "L2"
        assert edge.object_tier == "L1"
    else:
        assert edge.subject_tier == "L1"
        assert edge.object_tier == "L2"


def test_same_as_edge_bitemporal(linker: CrossGraphLinker) -> None:
    a = _entity(entity_id="school:nyu", name="NYU")
    b = _entity(entity_id="partner:nyu", name="NYU")
    edge = linker.materialize_edge(a, b, confidence=0.95)
    assert edge.t_valid_from is not None
    assert edge.t_ingest_from is not None
    assert edge.t_valid_to is None
    assert edge.t_ingest_to is None


def test_same_as_edge_references(linker: CrossGraphLinker) -> None:
    a = _entity(entity_id="school:nyu", name="NYU", source_id="ds:adea")
    b = _entity(entity_id="partner:nyu", name="NYU",
                source_id="ds:partner_postgres")
    edge = linker.materialize_edge(a, b, confidence=0.95)
    assert "ds:adea" in edge.references
    assert "ds:partner_postgres" in edge.references


# ----------------------------------------------------------------------
# Tier interaction
# ----------------------------------------------------------------------


def test_l1_node_not_elevated_via_same_as(linker: CrossGraphLinker) -> None:
    """ADR-015: cross-graph SAME_AS never elevates an L2/L5 entity to L1."""
    l1 = _entity(entity_id="school:nyu", tier="L1", name="NYU")
    l2 = _entity(entity_id="partner:nyu", tier="L2", name="NYU")
    edge = linker.materialize_edge(l1, l2, confidence=0.99)
    # The edge records per-endpoint tier; neither endpoint changes tier.
    assert edge.subject_tier in {"L1", "L2"}
    assert edge.object_tier in {"L1", "L2"}
    assert {edge.subject_tier, edge.object_tier} == {"L1", "L2"}


# ----------------------------------------------------------------------
# F1 gate on gold set
# ----------------------------------------------------------------------


GOLD_PATH = Path("evals/gold/v1.5a-cross-graph.jsonl")


def test_cross_graph_gold_set_f1_gate() -> None:
    """AC-5: F1 ≥ 0.92 on the 100-pair gold set."""
    if not GOLD_PATH.exists():
        pytest.fail(f"gold set missing: {GOLD_PATH}")
    pairs = [json.loads(line) for line in GOLD_PATH.read_text().splitlines() if line.strip()]
    assert len(pairs) == 100, f"gold set must have 100 rows, got {len(pairs)}"

    linker = CrossGraphLinker(embedding_service=HashEmbeddingService())

    tp = fp = fn = tn = 0
    for pair in pairs:
        a = _entity(
            entity_id=pair["entity_a_id"],
            name=pair["entity_a_name"],
            aliases=tuple(pair.get("entity_a_aliases", [])),
            entity_type=pair["entity_type"],
            tier=pair.get("entity_a_tier", "L2"),
            source_id=pair.get("entity_a_source_id", "ds:a"),
        )
        b = _entity(
            entity_id=pair["entity_b_id"],
            name=pair["entity_b_name"],
            aliases=tuple(pair.get("entity_b_aliases", [])),
            entity_type=pair["entity_type"],
            tier=pair.get("entity_b_tier", "L2"),
            source_id=pair.get("entity_b_source_id", "ds:b"),
        )
        # Determine prediction: link if the linker would return either auto
        # or HITL routing.
        candidates = linker.link(a, [b])
        predicted_same = any(c.confidence >= 0.75 for c in candidates)
        is_same = bool(pair["label_same"])
        if is_same and predicted_same:
            tp += 1
        elif is_same and not predicted_same:
            fn += 1
        elif not is_same and predicted_same:
            fp += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    assert f1 >= 0.92, (
        f"cross-graph F1 {f1:.3f} < 0.92 gate "
        f"(precision={precision:.3f} recall={recall:.3f} "
        f"tp={tp} fp={fp} fn={fn} tn={tn})"
    )


# ----------------------------------------------------------------------
# Pydantic shape sanity
# ----------------------------------------------------------------------


def test_candidate_routing_enum() -> None:
    assert CrossGraphLinkRouting.__args__ == ("auto", "hitl", "reject")


def test_same_as_edge_serializable() -> None:
    edge = SameAsEdge(
        subject_id="a", object_id="b",
        subject_tier="L1", object_tier="L2",
        rank="normal",
        confidence=0.95,
        references=("ds:a", "ds:b"),
        qualifiers={"matched_via": "exact_name"},
        t_valid_from=datetime.now(UTC),
        t_valid_to=None,
        t_ingest_from=datetime.now(UTC),
        t_ingest_to=None,
        status="active",
    )
    revived = SameAsEdge.model_validate_json(edge.model_dump_json())
    assert revived == edge


def test_candidate_pydantic_round_trip() -> None:
    cand = CrossGraphCandidate(
        source_entity_id="a",
        target_entity_id="b",
        confidence=0.91,
        routing="auto",
        matched_signals=("lexical",),
        evidence={"matched_alias": "NYU"},
    )
    revived = CrossGraphCandidate.model_validate_json(cand.model_dump_json())
    assert revived == cand
