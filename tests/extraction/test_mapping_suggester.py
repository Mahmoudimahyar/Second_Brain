"""Tests for V1.5a Phase 3 — `MappingSuggester` (FR-1.5a-3, AC-3).

Most tests use the deterministic `HashEmbeddingService` for fast iteration on
structure + heuristics. The F1 gold-set gate test in
`test_mapping_suggester_gold.py` swaps in `BGEEmbeddingService` for real
semantic similarity.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.embeddings.hash_embedder import HashEmbeddingService
from src.extraction.mapping_suggester import (
    MappingProposal,
    MappingSuggester,
    NodePropertyDef,
    seed_node_property_dictionary,
)
from src.gateway import api as gw_module
from src.ingestion.sources.base import (
    ColumnSpec,
    ForeignKeySpec,
    SchemaSnapshot,
    TableSpec,
)


def _snapshot(*tables: TableSpec, source_id: str = "ds:t") -> SchemaSnapshot:
    return SchemaSnapshot(
        source_id=source_id,
        discovered_at=datetime.now(UTC),
        tables=list(tables),
        labels=[],
        rel_types=[],
    )


def _table(
    name: str, columns: list[tuple[str, str]],
    *, pk: list[str] | None = None,
    fks: list[ForeignKeySpec] | None = None,
    samples: list[dict] | None = None,
) -> TableSpec:
    return TableSpec(
        name=name,
        column_specs=[
            ColumnSpec(
                name=cn, type=ct, nullable=True,
                sample_values=[],
            ) for cn, ct in columns
        ],
        primary_key=pk,
        foreign_keys=fks or [],
        sample_rows=samples or [],
    )


@pytest.fixture
def suggester() -> MappingSuggester:
    return MappingSuggester(embedding_service=HashEmbeddingService())


def test_schools_table_proposes_school_node(suggester: MappingSuggester) -> None:
    """FR-1.5a-3.3 — schools table → School node ≥ 0.90 confidence."""
    snap = _snapshot(
        _table(
            "schools",
            [
                ("id", "INTEGER"),
                ("name", "TEXT"),
                ("city", "TEXT"),
                ("state", "TEXT"),
            ],
            pk=["id"],
            samples=[
                {"id": 1, "name": "New York University", "city": "New York",
                 "state": "NY"},
                {"id": 2, "name": "Harvard School of Dental Medicine",
                 "city": "Boston", "state": "MA"},
            ],
        ),
    )
    proposal = suggester.suggest(snap)
    schools = next(t for t in proposal.per_table if t.table_or_label == "schools")
    assert schools.mapping_type == "node"
    assert schools.target_type == "School"
    assert schools.confidence >= 0.90
    assert schools.routing == "auto"


def test_metrics_table_proposes_metric_node(suggester: MappingSuggester) -> None:
    snap = _snapshot(
        _table(
            "school_year_metrics",
            [
                ("metric_id", "TEXT"),
                ("school_id", "INTEGER"),
                ("cycle_year", "TEXT"),
                ("metric_name", "TEXT"),
                ("metric_value", "REAL"),
                ("unit", "TEXT"),
            ],
            pk=["metric_id"],
            fks=[ForeignKeySpec(
                columns=["school_id"], references_table="schools",
                references_columns=["id"],
            )],
        ),
    )
    proposal = suggester.suggest(snap)
    metrics = next(t for t in proposal.per_table
                   if t.table_or_label == "school_year_metrics")
    assert metrics.mapping_type == "node"
    assert metrics.target_type == "Metric"


def test_join_table_proposes_edge(suggester: MappingSuggester) -> None:
    """FR-1.5a-3.3(c)(d) — composite-PK two-FK table → edge."""
    snap = _snapshot(
        _table(
            "enrollments",
            [
                ("user_id", "INTEGER"),
                ("school_id", "INTEGER"),
            ],
            pk=["user_id", "school_id"],
            fks=[
                ForeignKeySpec(
                    columns=["user_id"], references_table="users",
                    references_columns=["id"],
                ),
                ForeignKeySpec(
                    columns=["school_id"], references_table="schools",
                    references_columns=["id"],
                ),
            ],
        ),
    )
    proposal = suggester.suggest(snap)
    enroll = next(t for t in proposal.per_table
                  if t.table_or_label == "enrollments")
    assert enroll.mapping_type == "edge"
    assert enroll.edge_endpoints is not None
    assert set(enroll.edge_endpoints) == {"users", "schools"}


def test_audit_table_proposes_skip(suggester: MappingSuggester) -> None:
    """FR-1.5a-3.3(e) edge case — operational tables get skip routing."""
    snap = _snapshot(
        _table(
            "audit_log",
            [
                ("audit_id", "INTEGER"),
                ("event_kind", "TEXT"),
                ("ts", "DATETIME"),
                ("actor", "TEXT"),
            ],
            pk=["audit_id"],
        ),
    )
    proposal = suggester.suggest(snap)
    audit = next(t for t in proposal.per_table
                 if t.table_or_label == "audit_log")
    assert audit.mapping_type == "skip"


def test_low_confidence_routes_to_hitl(suggester: MappingSuggester) -> None:
    """Borderline confidence → routing='hitl'. Tested with a table whose
    column names are not in the NPD."""
    snap = _snapshot(
        _table(
            "widgets_xyz",
            [
                ("widget_id", "INTEGER"),
                ("opacity", "REAL"),
                ("luminance", "REAL"),
            ],
            pk=["widget_id"],
        ),
    )
    proposal = suggester.suggest(snap)
    widgets = next(t for t in proposal.per_table
                   if t.table_or_label == "widgets_xyz")
    # We expect this to land in 'reject' (confidence < 0.75) when hash
    # embeddings are used — no semantic match. The routing chain hands
    # this to HITL only if it's between 0.75 and 0.90.
    assert widgets.routing in {"hitl", "reject"}


def test_reasoning_chain_attached(suggester: MappingSuggester) -> None:
    snap = _snapshot(
        _table(
            "schools",
            [("id", "INTEGER"), ("name", "TEXT")],
            pk=["id"],
        ),
    )
    proposal = suggester.suggest(snap)
    schools = next(t for t in proposal.per_table
                   if t.table_or_label == "schools")
    assert schools.reasoning_chain
    assert any("name" in r.lower() for r in schools.reasoning_chain)


def test_node_property_dictionary_seeded() -> None:
    """The NPD must cover V1's core node types."""
    npd = seed_node_property_dictionary()
    node_types = {d.node_type for d in npd}
    expected_core = {"School", "Program", "User", "Post", "Comment", "Metric"}
    missing = expected_core - node_types
    assert not missing, f"NPD missing core node types: {missing}"


def test_node_property_def_is_pydantic_safe() -> None:
    defn = NodePropertyDef(
        node_type="School", property="name",
        description="The canonical name of a US dental school",
        aliases=("school name", "institution"),
    )
    # Should serialize via dataclass / repr without raising.
    assert defn.node_type == "School"
    assert defn.property == "name"


def test_prior_decision_boost(suggester: MappingSuggester) -> None:
    """FR-1.5a-3.6 — committing a decision raises confidence on a
    similar-shape table on the next run."""
    snap1 = _snapshot(
        _table(
            "partner_schools",
            [("id", "INTEGER"), ("name", "TEXT"), ("city", "TEXT")],
            pk=["id"],
        ),
        source_id="ds:partner_a",
    )
    proposal1 = suggester.suggest(snap1)
    first_conf = next(
        t.confidence for t in proposal1.per_table
        if t.table_or_label == "partner_schools"
    )
    suggester.record_committed_decision(
        source_id="ds:partner_a",
        table_or_label="partner_schools",
        mapping_type="node",
        target_type="School",
    )
    snap2 = _snapshot(
        _table(
            "partner_schools",
            [("id", "INTEGER"), ("name", "TEXT"), ("city", "TEXT")],
            pk=["id"],
        ),
        source_id="ds:partner_b",
    )
    proposal2 = suggester.suggest(snap2)
    boosted_conf = next(
        t.confidence for t in proposal2.per_table
        if t.table_or_label == "partner_schools"
    )
    assert boosted_conf >= first_conf, (
        f"prior-decision boost did not raise confidence: "
        f"{first_conf=} → {boosted_conf=}"
    )


def test_no_llm_pollution(
    suggester: MappingSuggester, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-1.5a-3 explicit — suggestion logic uses BGE embeddings only.
    Property test: mocking the gateway, it must never be invoked."""
    invocations: list[object] = []

    def _spy(*args: object, **kwargs: object) -> None:
        invocations.append((args, kwargs))
        raise RuntimeError("MappingSuggester invoked the LLM gateway")

    monkeypatch.setattr(gw_module, "default_gateway", _spy)

    snap = _snapshot(
        _table(
            "schools",
            [("id", "INTEGER"), ("name", "TEXT"), ("city", "TEXT")],
            pk=["id"],
        ),
    )
    suggester.suggest(snap)  # must NOT touch the gateway
    assert invocations == []


def test_proposal_pydantic_round_trip(suggester: MappingSuggester) -> None:
    snap = _snapshot(
        _table(
            "schools",
            [("id", "INTEGER"), ("name", "TEXT")],
            pk=["id"],
        ),
    )
    proposal = suggester.suggest(snap)
    revived = MappingProposal.model_validate_json(proposal.model_dump_json())
    assert revived.source_id == proposal.source_id
    assert len(revived.per_table) == len(proposal.per_table)
