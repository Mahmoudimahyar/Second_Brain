"""WP3.4 — resolve_pass4_conflicts runs the wired resolver over real Claim nodes."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.conflict.joint_resolver import L1AnchoredJointResolver
from src.conflict.judge import ThreeVendorJudge
from src.conflict.pass4_resolution import (
    _node_to_claim,
    build_joint_resolver_if_enabled,
    resolve_pass4_conflicts,
)
from src.conflict.resolver import ConflictResolver
from src.gateway.api import MockProvider
from src.graph.client import Node
from src.graph.kuzu_client import KuzuGraphClient

# Fixed "now" so HALO-decay-dependent assertions don't drift with wall-clock.
_NOW = datetime(2026, 5, 30, tzinfo=UTC)


def _voter(winner: str):
    def fixture(_prompt: str) -> str:
        return f'{{"winner_claim_id": "{winner}"}}'
    return fixture


def _claim_node(g: KuzuGraphClient, cid: str, value: str, *, vendor: str = "openai") -> None:
    g.upsert_node(Node(
        id=cid, label="Claim", source_tier="L5",
        properties={
            "subject": "school:nyu", "predicate": "casper_required",
            "value": value, "vendor": vendor, "confidence": 0.9,
        },
    ))


def test_resolves_same_tier_tie_and_marks_loser(tmp_path: Path) -> None:
    g = KuzuGraphClient(db_path=tmp_path / "kuzu.db")
    _claim_node(g, "claim:a", "yes")
    _claim_node(g, "claim:b", "no")
    judge = ThreeVendorJudge(clients=[
        MockProvider(vendor="anthropic", fixture=_voter("claim:a")),
        MockProvider(vendor="openai", fixture=_voter("claim:a")),
        MockProvider(vendor="gemini", fixture=_voter("claim:a")),
    ])
    report = resolve_pass4_conflicts(
        g, ConflictResolver(judge=judge), ingest_time=datetime.now(UTC),
    )
    assert report.conflict_groups == 1
    assert report.judge_resolved == 1
    loser = g.get_node("claim:b")
    assert loser is not None
    assert loser.properties.get("resolution_status") == "superseded_by_judge"
    g.close()


def test_no_conflict_when_single_claim_per_group(tmp_path: Path) -> None:
    g = KuzuGraphClient(db_path=tmp_path / "kuzu.db")
    _claim_node(g, "claim:a", "yes")
    report = resolve_pass4_conflicts(
        g, ConflictResolver(), ingest_time=datetime.now(UTC),
    )
    assert report.conflict_groups == 0
    g.close()


def test_lone_resolver_without_judge_sends_tie_to_hitl(tmp_path: Path) -> None:
    g = KuzuGraphClient(db_path=tmp_path / "kuzu.db")
    _claim_node(g, "claim:a", "yes")
    _claim_node(g, "claim:b", "no")
    report = resolve_pass4_conflicts(
        g, ConflictResolver(), ingest_time=datetime.now(UTC),  # no judge
    )
    assert report.conflict_groups == 1
    assert report.hitl_pending == 1
    g.close()


# -- ADR-026 joint resolver: set-based path through resolve_pass4_conflicts ----


def _tier_claim(
    g: KuzuGraphClient, cid: str, value: str, *, tier: str, cycle_year: str,
    cred: float = 0.5, subject: str = "school:ucla",
    predicate: str = "tuition_resident",
) -> None:
    g.upsert_node(Node(
        id=cid, label="Claim", source_tier=tier,
        properties={
            "subject": subject, "predicate": predicate, "value": value,
            "vendor": "openai", "confidence": 0.9, "credibility": cred,
            "cycle_year": cycle_year,
        },
    ))


def test_joint_resolver_current_l1_invalidates_corroborated_rumor(tmp_path: Path) -> None:
    """C3 on the real path: a current L1 protects against a 3x-corroborated wrong
    L5 majority; the rumor claims are marked, the L1 claim is never mutated."""
    g = KuzuGraphClient(db_path=tmp_path / "kuzu.db")
    _tier_claim(g, "claim:l1", "0", tier="L1", cycle_year="2024-25", cred=1.0)
    for i in range(3):
        _tier_claim(g, f"claim:r{i}", "70000", tier="L5", cycle_year="2025-26")
    report = resolve_pass4_conflicts(
        g, ConflictResolver(), ingest_time=_NOW,
        joint_resolver=L1AnchoredJointResolver(),
    )
    assert report.conflict_groups == 1
    assert report.l1_clash == 1
    assert g.get_node("claim:l1").properties.get("resolution_status") is None
    assert g.get_node("claim:r0").properties.get("resolution_status") == (
        "invalidated_by_official"
    )
    g.close()


def test_joint_resolver_stale_l1_corrected_never_mutates_l1(tmp_path: Path) -> None:
    """C2 on the real path: a 5-year-stale L1 yields to a fresh corroborated L5
    correction (trust_weighted) — but the L1 claim node is still not mutated."""
    g = KuzuGraphClient(db_path=tmp_path / "kuzu.db")
    _tier_claim(g, "claim:l1", "no", tier="L1", cycle_year="2021-22", cred=1.0,
                predicate="casper_required")
    for i in range(3):
        _tier_claim(g, f"claim:f{i}", "yes", tier="L5", cycle_year="2025-26",
                    cred=0.6, predicate="casper_required")
    report = resolve_pass4_conflicts(
        g, ConflictResolver(), ingest_time=_NOW,
        joint_resolver=L1AnchoredJointResolver(),
    )
    assert report.conflict_groups == 1
    assert report.trust_weighted == 1
    # non-negotiable #1: stale L1 loser is never mutated.
    assert g.get_node("claim:l1").properties.get("resolution_status") is None
    # the winning fresh L5 claims are not marked as losers either.
    assert g.get_node("claim:f0").properties.get("resolution_status") is None
    g.close()


# -- temporal mapping (the t_valid_from fix) + flag gate ------------------------


def test_node_to_claim_maps_cycle_year_to_t_valid_from() -> None:
    node = Node(id="c", label="Claim", source_tier="L5", properties={
        "subject": "s", "predicate": "p", "value": "v", "cycle_year": "2024-25"})
    assert _node_to_claim(node).t_valid_from == datetime(2024, 1, 1, tzinfo=UTC)


def test_node_to_claim_falls_back_to_ingest_iso() -> None:
    node = Node(id="c", label="Claim", source_tier="L5", properties={
        "subject": "s", "predicate": "p", "value": "v",
        "ingest_iso": "2023-06-01T00:00:00+00:00"})
    t = _node_to_claim(node).t_valid_from
    assert t is not None and t.year == 2023


def test_node_to_claim_no_temporal_is_none() -> None:
    node = Node(id="c", label="Claim", source_tier="L5", properties={
        "subject": "s", "predicate": "p", "value": "v"})
    assert _node_to_claim(node).t_valid_from is None


def test_joint_resolver_flag_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECBRAIN_JOINT_RESOLVER", raising=False)
    assert build_joint_resolver_if_enabled() is None
    monkeypatch.setenv("SECBRAIN_JOINT_RESOLVER", "1")
    assert isinstance(build_joint_resolver_if_enabled(), L1AnchoredJointResolver)
