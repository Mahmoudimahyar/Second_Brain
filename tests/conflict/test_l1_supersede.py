"""Tests for GAP-053 — bitemporal L1 Claim supersession (ADR-005).

Uses an in-memory Kùzu database so no disk fixture is needed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.conflict.l1_claims import supersede_l1_claim_if_changed, _claim_node
from src.graph.client import Node


# ---------------------------------------------------------------------------
# Minimal mock graph that supports get_node + upsert_node
# ---------------------------------------------------------------------------

class MockGraph:
    """In-memory store; mimics KuzuGraphClient.get_node + upsert_node."""

    def __init__(self) -> None:
        self._store: dict[str, Node] = {}

    def get_node(self, node_id: str) -> Node | None:
        return self._store.get(node_id)

    def upsert_node(self, node: Node) -> None:
        self._store[node.id] = node

    def all_nodes(self):
        return list(self._store.values())


def _at(year: int = 2026, month: int = 1, day: int = 1) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def _make_claim(value, dump_id: str = "dump_v1") -> Node:
    return _claim_node(
        canonical_id="school:nyu",
        predicate="board_pass_rate",
        value=value,
        cycle_year="2025-26",
        source_dump_id=dump_id,
    )


# ---------------------------------------------------------------------------
# supersede_l1_claim_if_changed
# ---------------------------------------------------------------------------

class TestSupersedeLl1ClaimIfChanged:
    def test_no_prior_node_returns_new_claim_no_supersede(self):
        g = MockGraph()
        claim = _make_claim(0.95)
        result, did = supersede_l1_claim_if_changed(g, claim, at=_at())
        assert did is False
        assert result.id == claim.id
        assert result.properties["value"] == 0.95

    def test_same_value_is_idempotent(self):
        g = MockGraph()
        claim = _make_claim(0.95)
        g.upsert_node(claim)
        result, did = supersede_l1_claim_if_changed(g, claim, at=_at())
        assert did is False
        assert result.id == claim.id

    def test_changed_value_creates_archive_node(self):
        g = MockGraph()
        old_claim = _make_claim(0.95)
        g.upsert_node(old_claim)

        new_claim = _make_claim(0.97, dump_id="dump_v2")
        result, did = supersede_l1_claim_if_changed(g, new_claim, at=_at(2026, 2, 1))

        assert did is True
        # Archive node must exist
        archive_keys = [k for k in g._store if "superseded" in k]
        assert len(archive_keys) == 1
        archive = g._store[archive_keys[0]]
        assert archive.properties["value"] == 0.95
        assert archive.properties["active"] is False
        assert "superseded_at" in archive.properties

    def test_changed_value_result_has_supersedes_reference(self):
        g = MockGraph()
        old_claim = _make_claim(0.95)
        g.upsert_node(old_claim)

        new_claim = _make_claim(0.97, dump_id="dump_v2")
        result, _ = supersede_l1_claim_if_changed(g, new_claim, at=_at(2026, 2, 1))

        assert result.properties.get("supersedes") == old_claim.id
        assert result.properties.get("active") is True

    def test_result_id_is_canonical_not_archived(self):
        g = MockGraph()
        old_claim = _make_claim(0.95)
        g.upsert_node(old_claim)

        new_claim = _make_claim(0.98)
        result, _ = supersede_l1_claim_if_changed(g, new_claim, at=_at())
        # Canonical id is unchanged (not versioned); archive gets the timestamped suffix
        assert result.id == old_claim.id
        assert "superseded" not in result.id

    def test_string_and_numeric_value_comparison(self):
        g = MockGraph()
        # Existing node with string "0.95"
        old = _make_claim("0.95")
        g.upsert_node(old)
        # New node with float 0.95 → str("0.95") == str("0.95") → idempotent
        new = _make_claim(0.95)
        result, did = supersede_l1_claim_if_changed(g, new, at=_at())
        assert did is False, "str(0.95) == '0.95' → should be idempotent"

    def test_archive_timestamp_in_node_id(self):
        g = MockGraph()
        g.upsert_node(_make_claim(100))
        at = datetime(2026, 3, 15, 12, 30, 0, tzinfo=timezone.utc)
        supersede_l1_claim_if_changed(g, _make_claim(200), at=at)
        archive_id = next(k for k in g._store if "superseded" in k)
        assert "20260315T123000" in archive_id

    def test_superseded_by_dump_recorded(self):
        g = MockGraph()
        g.upsert_node(_make_claim(100, dump_id="dump_v1"))
        new = _make_claim(200, dump_id="dump_v2")
        supersede_l1_claim_if_changed(g, new, at=_at())
        archive = next(n for n in g._store.values() if "superseded" in n.id)
        assert archive.properties["superseded_by_dump"] == "dump_v2"

    def test_uses_utc_now_when_at_not_provided(self):
        g = MockGraph()
        g.upsert_node(_make_claim(100))
        result, did = supersede_l1_claim_if_changed(g, _make_claim(200))
        assert did is True
        archive = next(n for n in g._store.values() if "superseded" in n.id)
        assert "superseded_at" in archive.properties


# ---------------------------------------------------------------------------
# build_db_fact_claims integration (check_supersede flag)
# ---------------------------------------------------------------------------

class TestBuildDbFactClaimsSupersede:
    def test_check_supersede_false_does_not_call_get_node(self):
        from src.conflict.l1_claims import build_db_fact_claims

        g = MockGraph()
        school_node = Node(
            id="school:nyu", label="School", source_tier="L1",
            properties={"canonical_name": "NYU", "avg_board_pass_rate": 0.95},
        )
        g.upsert_node(school_node)

        claims = build_db_fact_claims(g, source_dump_id="dump_v1", check_supersede=False)
        # claim for board_pass_rate should exist
        ids = [c.id for c in claims]
        assert any("board_pass_rate" in cid for cid in ids)
        # No archive nodes created (supersede was off)
        archive_keys = [k for k in g._store if "superseded" in k]
        assert archive_keys == []

    def test_check_supersede_true_creates_archive_on_value_change(self):
        from src.conflict.l1_claims import build_db_fact_claims

        g = MockGraph()
        # Pre-load existing claim with old value
        old_claim = _claim_node(
            canonical_id="school:nyu", predicate="board_pass_rate",
            value=0.90, cycle_year="2024-25", source_dump_id="dump_v1",
        )
        g.upsert_node(old_claim)
        # School node with new value
        g.upsert_node(Node(
            id="school:nyu", label="School", source_tier="L1",
            properties={"canonical_name": "NYU", "avg_board_pass_rate": 0.95},
        ))

        claims = build_db_fact_claims(
            g, source_dump_id="dump_v2", check_supersede=True, at=_at(2026, 2, 1),
        )
        archive_keys = [k for k in g._store if "superseded" in k]
        assert len(archive_keys) == 1
        assert g._store[archive_keys[0]].properties["value"] == 0.90
        # Returned claim has new value
        bp_claims = [c for c in claims if "board_pass_rate" in c.id]
        assert len(bp_claims) == 1
        assert bp_claims[0].properties.get("supersedes") == old_claim.id
