"""Emit L1 gold facts as `Claim` nodes so the ADR-026 resolver's L1 anchor fires
on **organic** L5 forum conflicts (not only seeded ones).

The ADR-026 `L1AnchoredJointResolver` (and the deterministic cascade) adjudicate
`(subject, predicate)` groups of `Claim` nodes. Until now L1 gold facts lived as
`School`/`Program` node *properties* and ADEA metrics as SQLite rows — never as
`Claim` nodes — so a forum claim about a school's tuition/board-pass-rate had no
L1 claim to clash with. This module materializes those gold facts as immutable
L1 `Claim` nodes:

  - **DB facts** (`build_db_fact_claims`) from the `School`/`Program` L1 nodes —
    board pass rate, interview-required, positions, stipend, …; clean predicate
    names that match the Pass-4 conflict vocabulary.
  - **ADEA metrics** (`build_adea_metric_claims`) from `l1_school_year_metric` —
    the headline forum metric, resident/non-resident tuition, with the raw ADEA
    table-header metric names normalized to `tuition_resident` /
    `tuition_nonresident` and carrying their real `cycle_year`.

Subject ids are the canonical entity ids; predicates align with what Pass-4
extracts. `canonicalize_subject` resolves an L5 claim's raw subject text to a
canonical id so L1 and L5 claims land in the same group.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from src.graph.client import Node

if TYPE_CHECKING:
    from pathlib import Path

    from src.er.canonical_index import CanonicalIndex
    from src.graph.kuzu_client import KuzuGraphClient

# DB School-node fact column -> Pass-4-aligned predicate. These are the
# forum-discussed, cross-checkable facts (not every column).
_SCHOOL_FACT_PREDICATES: dict[str, str] = {
    "avg_board_pass_rate": "board_pass_rate",
    "interview_required": "interview_required",
    "degree_offered": "degree_offered",
    "is_ivy_league": "is_ivy_league",
    "program_length_months": "program_length_months",
    "job_placement_rate": "job_placement_rate",
}
# Residency Program-node fact column -> predicate.
_PROGRAM_FACT_PREDICATES: dict[str, str] = {
    "positions_available": "positions_available",
    "program_length_months": "program_length_months",
    "stipend_offered": "stipend_offered",
    "match_participating": "match_participating",
    "application_service": "application_service",
}

# Default cycle for DB facts (the DJ-Backup is the current snapshot).
DB_FACT_CYCLE = "2025-26"


def normalize_adea_predicate(metric_name: str) -> str | None:
    """Map a raw ADEA `metric_name` to a clean predicate, or None to skip.

    ADEA headers read "... Resident and Non-Resident Tuition by Class, 2024-25
    - <qualifier>" — the body mentions *both* words, so resident/non-resident is
    decided by the trailing " - <qualifier>" only.
    """
    text = metric_name or ""
    if not re.search(r"tuition by class", text, re.I | re.S):
        return None
    qualifier = text.split(" - ")[-1].strip().lower()
    if re.search(r"non-?resident", qualifier):
        return "tuition_nonresident"
    if "resident" in qualifier:
        return "tuition_resident"
    return None


def _claim_node(
    *, canonical_id: str, predicate: str, value: Any, cycle_year: str,
    source_dump_id: str,
) -> Node:
    return Node(
        id=f"claim:l1:{canonical_id}:{predicate}",
        label="Claim",
        source_tier="L1",
        properties={
            "subject": canonical_id,
            "predicate": predicate,
            "value": value,
            "cycle_year": cycle_year,
            "credibility": 1.0,
            "confidence": 1.0,
            "vendor": "l1_gold",
            "source": "l1_fact",
            "source_dump_id": source_dump_id,
        },
    )


def build_adea_metric_claims(sqlite_path: Path, *, source_dump_id: str) -> list[Node]:
    """Emit L1 `Claim` nodes from ADEA `l1_school_year_metric` (tuition only)."""
    if not sqlite_path.is_file():
        return []
    claims: list[Node] = []
    conn = sqlite3.connect(sqlite_path)
    try:
        try:
            rows = conn.execute(
                "SELECT canonical_school_id, cycle_year, metric_name, metric_value "
                "FROM l1_school_year_metric",
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        # Latest cycle per (school, predicate) wins — avoid emitting stale dupes.
        latest: dict[tuple[str, str], tuple[str, Any]] = {}
        for school_id, cycle_year, metric_name, metric_value in rows:
            predicate = normalize_adea_predicate(str(metric_name))
            if predicate is None or metric_value is None:
                continue
            key = (str(school_id), predicate)
            prior = latest.get(key)
            if prior is None or str(cycle_year) > prior[0]:
                latest[key] = (str(cycle_year), metric_value)
        for (school_id, predicate), (cycle_year, value) in latest.items():
            claims.append(_claim_node(
                canonical_id=school_id, predicate=predicate, value=value,
                cycle_year=cycle_year, source_dump_id=source_dump_id,
            ))
    finally:
        conn.close()
    return claims


def supersede_l1_claim_if_changed(
    graph: "KuzuGraphClient",
    new_claim: Node,
    *,
    at: datetime | None = None,
) -> tuple[Node, bool]:
    """Bitemporally version an L1 Claim node when its value changes on re-ingest.

    This is the caller for ``supersede_edge()``'s logical equivalent in the
    claim-as-node model (GAP-053 / ADR-005). Edges don't carry the claim value
    directly in V1; instead we archive the superseded node and tag the new one
    with a ``supersedes`` back-reference.

    Returns ``(claim_to_upsert, did_supersede)``:
      - No prior node        → ``(new_claim, False)`` — caller upserts normally.
      - Same value (idempotent) → ``(existing_node, False)`` — skip upsert.
      - Value changed        → archives old node, returns ``(new_claim+metadata, True)``.
    """
    at = at or datetime.now(tz=timezone.utc)
    existing = graph.get_node(new_claim.id)
    if existing is None:
        return new_claim, False

    old_val = existing.properties.get("value")
    new_val = new_claim.properties.get("value")
    # Normalise to string for comparison so int/float round-trips don't false-positive
    if str(old_val) == str(new_val):
        return existing, False   # idempotent — nothing changed

    # Archive the superseded node under a timestamped id
    at_tag = at.strftime("%Y%m%dT%H%M%S")
    archive_id = f"{existing.id}:superseded:{at_tag}"
    archive_node = Node(
        id=archive_id,
        label=existing.label,
        source_tier=existing.source_tier,
        properties={
            **existing.properties,
            "superseded_at": at.isoformat(),
            "superseded_by_dump": new_claim.properties.get("source_dump_id", ""),
            "active": False,
        },
    )
    graph.upsert_node(archive_node)

    # Return updated new_claim with provenance
    updated_claim = Node(
        id=new_claim.id,
        label=new_claim.label,
        source_tier=new_claim.source_tier,
        properties={**new_claim.properties, "supersedes": existing.id, "active": True},
    )
    return updated_claim, True


def build_db_fact_claims(
    graph: "KuzuGraphClient",
    *,
    source_dump_id: str,
    cycle_year: str = DB_FACT_CYCLE,
    check_supersede: bool = False,
    at: datetime | None = None,
) -> list[Node]:
    """Emit L1 ``Claim`` nodes from ``School`` + ``Program`` L1 node fact properties.

    When ``check_supersede=True``, each new Claim is compared against the
    currently-stored node via ``supersede_l1_claim_if_changed()`` (GAP-053).
    Pass ``at`` to override the supersede timestamp (useful for testing).
    """
    ingest_time = at or datetime.now(tz=timezone.utc)
    claims: list[Node] = []
    for node in graph.all_nodes():
        if node.source_tier != "L1":
            continue
        if node.label == "School":
            fact_map = _SCHOOL_FACT_PREDICATES
        elif node.label == "Program":
            fact_map = _PROGRAM_FACT_PREDICATES
        else:
            continue
        for col, predicate in fact_map.items():
            value = node.properties.get(col)
            if value is None or value == "":
                continue
            claim = _claim_node(
                canonical_id=node.id, predicate=predicate, value=value,
                cycle_year=cycle_year, source_dump_id=source_dump_id,
            )
            if check_supersede:
                claim, _ = supersede_l1_claim_if_changed(graph, claim, at=ingest_time)
            claims.append(claim)
    return claims


def canonicalize_subject(subject: str, index: CanonicalIndex) -> str:
    """Resolve an L5 claim's raw subject text to a canonical id when possible.

    L1 claims already carry canonical ids (``school:``/``specialty:``/…). L5
    Pass-4 claims store the raw mention text ("UCLA"); resolving it to the same
    canonical id lets the two land in one ``(subject, predicate)`` group.
    """
    if not subject:
        return subject
    if ":" in subject and subject.split(":", 1)[0] in {
        "school", "specialty", "institution", "program",
    }:
        return subject
    alias_map = index.aliases()
    hit = alias_map.get(subject) or alias_map.get(subject.strip())
    if hit:
        return hit
    # case-insensitive fallback
    low = subject.strip().lower()
    for alias, cid in alias_map.items():
        if alias.lower() == low:
            return cid
    return subject
