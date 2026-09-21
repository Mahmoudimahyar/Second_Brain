"""Run the conflict resolver over Pass-4 `Claim` nodes on the real path (GAP-052).

Pass 4 writes `Claim` nodes (subject / predicate / value / vendor / cycle_year).
This reads them back, groups by (subject, predicate), and reconciles each
multi-claim group through `ConflictResolver` — which, when wired with a judge,
sends same-tier same-year ties to the 3-vendor panel (ADR-024) instead of
straight to HITL. Losing non-L1 claims are marked with a `resolution_status`
(L1 nodes are never mutated — non-negotiable #1).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from src.conflict.joint_resolver import JointResolution, L1AnchoredJointResolver
from src.conflict.judge import _family_of
from src.conflict.l1_claims import canonicalize_subject
from src.conflict.resolver import (
    Claim,
    ConflictResolver,
    ResolutionOutcome,
    ResolutionStatus,
)
from src.graph.client import Node
from src.graph.kuzu_client import KuzuGraphClient
from src.shared.timestamps import from_iso

if TYPE_CHECKING:
    from src.er.canonical_index import CanonicalIndex

_CYCLE_YEAR_RE = re.compile(r"\s*(\d{4})")


@dataclass(frozen=True)
class ResolutionReport:
    conflict_groups: int = 0
    judge_resolved: int = 0
    trust_weighted: int = 0
    l1_clash: int = 0
    hitl_pending: int = 0
    other: int = 0


_STATUS_LABEL: dict[ResolutionStatus, str] = {
    ResolutionStatus.L1_CLASH_INVALIDATED: "invalidated_by_official",
    ResolutionStatus.JUDGE_RESOLVED: "superseded_by_judge",
    ResolutionStatus.TRUST_WEIGHTED: "superseded_by_trust",
    ResolutionStatus.WEB_VERIFIED: "superseded_by_web_verify",
}


def _claim_t_valid_from(p: dict[str, Any]) -> datetime | None:
    """Temporal anchor for HALO decay + the cascade's temporal step.

    Prefer the application-cycle year the claim is *about* (`cycle_year`, e.g.
    "2024-25" -> 2024-01-01); fall back to the ingest timestamp (`ingest_iso`).
    Without this, every Pass-4 claim has `t_valid_from=None` and HALO decay
    collapses to 1.0 — making recency inert on the real path (the bug that
    silently neutered both the joint resolver and the cascade's temporal split).
    """

    cy = p.get("cycle_year")
    if cy:
        m = _CYCLE_YEAR_RE.match(str(cy))
        if m:
            return datetime(int(m.group(1)), 1, 1, tzinfo=UTC)
    iso = p.get("ingest_iso")
    if iso:
        try:
            return from_iso(str(iso))
        except (ValueError, TypeError):
            return None
    return None


def _node_to_claim(node: Node) -> Claim:
    p = node.properties
    # Prefer the normalized fields written by the 2026-06-09 resolution layer:
    # `resolved_school_id` (canonical school node id) + `predicate_canonical`
    # (14-bucket vocabulary). Raw `subject` is free text ("my state school") and
    # raw `predicate` has ~8k surface forms — without normalization L1 gold
    # claims and L5 forum claims never land in the same (subject, predicate)
    # group, so the ADR-026 L1 anchor never fires organically.
    return Claim(
        claim_id=node.id,
        subject_id=str(p.get("resolved_school_id") or p.get("subject") or ""),
        predicate=str(p.get("predicate_canonical") or p.get("predicate") or ""),
        object_value=p.get("value"),
        source_tier=node.source_tier,
        references=[str(p["source_post_id"])] if p.get("source_post_id") else [],
        t_valid_from=_claim_t_valid_from(p),
        confidence=float(p.get("confidence", 1.0)),
        credibility=float(p.get("credibility", 0.5)),
        extractor_family=_family_of(p.get("vendor")),
    )


def build_joint_resolver_if_enabled() -> L1AnchoredJointResolver | None:
    """ADR-026 — the L1-anchored joint-confidence resolver, gated off by default.

    Returns an `L1AnchoredJointResolver` only when `SECBRAIN_JOINT_RESOLVER=1`;
    otherwise `None` (the deterministic ADR-006 cascade stays the default).
    ADR-026 remains `proposed` until a real HITL-labeled conflict set justifies
    flipping the default — see `.agent/reports/v1.7-wp5-adr026-*`.
    """

    if os.environ.get("SECBRAIN_JOINT_RESOLVER") == "1":
        return L1AnchoredJointResolver()
    return None


def resolve_pass4_conflicts(
    graph: KuzuGraphClient,
    resolver: ConflictResolver,
    *,
    ingest_time: datetime,
    joint_resolver: L1AnchoredJointResolver | None = None,
    canonical_index: CanonicalIndex | None = None,
) -> ResolutionReport:
    """Reconcile every multi-claim (subject, predicate) group; mark losers.

    Default path folds the deterministic ADR-006 cascade pairwise. When a
    `joint_resolver` is supplied (ADR-026, flag-gated), each group is resolved
    set-wise by L1-anchored joint-confidence instead, with `ingest_time` as the
    HALO "now" for recency decay. L1 nodes are never mutated either way.

    When a `canonical_index` is supplied, each claim's raw subject text is
    resolved to its canonical entity id before grouping — so an L5 forum claim
    ("UCLA …") lands in the same group as the L1 gold claim (`school:ucla…`) and
    the L1 anchor actually fires on organic conflicts.
    """

    # Full-corpus read: the default nodes_of_label cap (10k) silently sliced the
    # 56k-claim corpus to its first storage-order rows — which excluded the L1
    # gold claims (written last), so the L1 anchor could never fire.
    claims = [_node_to_claim(n) for n in graph.nodes_of_label("Claim", limit=500_000)]
    if canonical_index is not None:
        claims = [
            replace(c, subject_id=canonicalize_subject(c.subject_id, canonical_index))
            for c in claims
        ]
    groups: dict[tuple[str, str], list[Claim]] = {}
    for c in claims:
        if c.subject_id and c.predicate:
            groups.setdefault((c.subject_id, c.predicate), []).append(c)

    report = ResolutionReport()
    for members in groups.values():
        if len(members) < 2:
            continue
        if joint_resolver is not None:
            outcome = _joint_to_outcome(
                joint_resolver.resolve_group(members, now=ingest_time),
            )
        else:
            new_claim, *existing = members
            outcome = resolver.reconcile(new_claim, existing)
        report = _tally(report, outcome)
        _mark_losers(graph, outcome)
    return report


def _joint_to_outcome(jr: JointResolution) -> ResolutionOutcome:
    """Adapt a `JointResolution` onto the shared `ResolutionOutcome` shape so the
    existing tally + loser-marking path is reused unchanged."""

    return ResolutionOutcome(
        status=jr.status,
        winning_claim=jr.winning_claim,
        losing_claims=jr.losing_claims,
        reason=jr.reason,
        low_confidence=jr.low_confidence,
    )


def _tally(report: ResolutionReport, outcome: ResolutionOutcome) -> ResolutionReport:
    inc = {
        "conflict_groups": report.conflict_groups + 1,
        "judge_resolved": report.judge_resolved,
        "trust_weighted": report.trust_weighted,
        "l1_clash": report.l1_clash,
        "hitl_pending": report.hitl_pending,
        "other": report.other,
    }
    match outcome.status:
        case ResolutionStatus.JUDGE_RESOLVED:
            inc["judge_resolved"] += 1
        case ResolutionStatus.TRUST_WEIGHTED:
            inc["trust_weighted"] += 1
        case ResolutionStatus.L1_CLASH_INVALIDATED:
            inc["l1_clash"] += 1
        case ResolutionStatus.HITL_PENDING:
            inc["hitl_pending"] += 1
        case _:
            inc["other"] += 1
    return ResolutionReport(**inc)


def _mark_losers(graph: KuzuGraphClient, outcome: ResolutionOutcome) -> None:
    label = _STATUS_LABEL.get(outcome.status)
    if label is None:
        return
    for loser in outcome.losing_claims:
        if loser.source_tier == "L1":  # non-negotiable #1: never mutate L1
            continue
        node = graph.get_node(loser.claim_id)
        if node is None:
            continue
        graph.upsert_node(Node(
            id=node.id, label=node.label, source_tier=node.source_tier,
            properties={**node.properties, "resolution_status": label},
        ))
