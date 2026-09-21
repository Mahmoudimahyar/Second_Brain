"""Tests for `src.retrieval.api.RetrievalService` (FR-8)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.er.canonical_index import CanonicalIndex
from src.graph.client import Edge, Node
from src.graph.kuzu_client import KuzuGraphClient
from src.retrieval import CanonicalEntity, QueryResult, RetrievalService


def _utc(year: int, month: int = 1, day: int = 1) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


def _seed_aliases(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE l1_school (
            canonical_id   TEXT PRIMARY KEY, canonical_name TEXT NOT NULL,
            city TEXT, state TEXT, country TEXT, ada_code TEXT, website TEXT,
            source_dump_id TEXT NOT NULL, created_utc TEXT NOT NULL
        );
        CREATE TABLE alias (
            alias_id TEXT PRIMARY KEY, canonical_id TEXT NOT NULL,
            alias_text TEXT NOT NULL, alias_source TEXT NOT NULL,
            confidence REAL, created_utc TEXT NOT NULL
        );
        """,
    )
    rows = [
        ("school:nyu", "NYU College of Dentistry", "manual"),
        ("school:harvard", "Harvard School of Dental Medicine", "manual"),
    ]
    for cid, name, src in rows:
        conn.execute(
            "INSERT INTO l1_school (canonical_id, canonical_name, source_dump_id, created_utc) "
            "VALUES (?, ?, ?, ?)",
            (cid, name, "dump:test", "2026-05-21T00:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO alias (alias_id, canonical_id, alias_text, alias_source, confidence, created_utc) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (f"alias:{cid}", cid, name, src, 1.0, "2026-05-21T00:00:00+00:00"),
        )
    conn.commit()
    conn.close()


def _make_service(tmp_path: Path) -> RetrievalService:
    side = tmp_path / "side.db"
    _seed_aliases(side)
    graph = KuzuGraphClient(db_path=tmp_path / "kuzu.db")
    index = CanonicalIndex(sqlite_path=side)
    return RetrievalService(graph=graph, canonical_index=index)


def _seed_graph(svc: RetrievalService) -> None:
    g = svc._graph
    g.upsert_node(Node(id="school:nyu", label="School", source_tier="L1",
                       properties={"canonical_name": "NYU College of Dentistry",
                                   "source_dump_id": "dump:adea24"}))
    g.upsert_node(Node(id="metric:nyu:tuition:2024-25", label="Metric",
                       source_tier="L1",
                       properties={"metric_name": "Tuition Resident",
                                   "metric_value": 94108.0,
                                   "cycle_year": "2024-25",
                                   "source_dump_id": "dump:adea24"}))
    g.upsert_node(Node(id="reddit_post:abc", label="Post", source_tier="L5",
                       properties={"title": "Help with NYU acceptance",
                                   "selftext": "looking for advice",
                                   "subreddit": "DentalSchool"}))
    g.upsert_edge(Edge(
        id="e1", label="SCHOOL_HAS_METRIC",
        from_id="school:nyu", to_id="metric:nyu:tuition:2024-25",
        source_tier="L1", rank="preferred",
        references=["dump:adea24", "Tab1!D5"],
        qualifiers={"cycle": "2024-25"},
        t_valid_from=_utc(2024, 9, 1), t_valid_to=_utc(2025, 8, 31),
        t_ingest_from=_utc(2026, 5, 21),
    ))
    g.upsert_edge(Edge(
        id="e2", label="MENTIONS_SCHOOL",
        from_id="reddit_post:abc", to_id="school:nyu",
        source_tier="L5", rank="normal",
        references=["reddit_post:abc"],
        t_valid_from=_utc(2020, 1, 1), t_ingest_from=_utc(2026, 5, 21),
    ))


def test_query_graph_finds_seed_by_substring(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    _seed_graph(svc)

    results = svc.query_graph("NYU", limit=10)

    assert len(results) >= 1
    found_ids = {r.node_id for r in results}
    assert "school:nyu" in found_ids
    svc._graph.close()


def test_query_graph_results_carry_references(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    _seed_graph(svc)

    results = svc.query_graph("nyu", traversal_depth=2)

    # NFR-4: every result carries references.
    missing = [r for r in results if not r.references]
    assert missing == []
    svc._graph.close()


def test_query_graph_returns_query_result_shape(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    _seed_graph(svc)

    results = svc.query_graph("NYU")

    for r in results:
        assert isinstance(r, QueryResult)
        assert r.node_id
        assert r.node_type
        assert r.source_tier in ("L1", "L2", "L3", "L4", "L5")
    svc._graph.close()


def test_query_graph_filters_by_source_tier_min(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    _seed_graph(svc)

    # source_tier_min="L1" → only L1 (excluding L5)
    results = svc.query_graph("nyu", source_tier_min="L1", traversal_depth=2)
    tiers = {r.source_tier for r in results}
    assert "L5" not in tiers
    svc._graph.close()


def test_query_graph_respects_as_of(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    _seed_graph(svc)

    # All edges ingested 2026-05-21. as_of=2026-01-01 → traverse no edges.
    results = svc.query_graph(
        "nyu", as_of=_utc(2026, 1, 1), traversal_depth=2,
    )
    # Seed school:nyu still returned (it's the substring hit), but no expanded
    # results via edges ingested after as_of.
    expanded = [r for r in results if r.path_explanation]
    assert expanded == []
    svc._graph.close()


def test_query_graph_traversal_depth_limits_expansion(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    _seed_graph(svc)

    shallow = svc.query_graph("nyu", traversal_depth=0, limit=50)
    deeper = svc.query_graph("nyu", traversal_depth=3, limit=50)
    assert len(deeper) >= len(shallow)
    svc._graph.close()


def test_query_graph_limit_is_respected(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    _seed_graph(svc)

    results = svc.query_graph("nyu", limit=1)
    assert len(results) <= 1
    svc._graph.close()


def test_query_graph_empty_query_returns_no_results(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    _seed_graph(svc)

    assert svc.query_graph("") == []
    assert svc.query_graph("   ") == []
    svc._graph.close()


def test_get_canonical_entity_returns_l1_match(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    _seed_graph(svc)

    canonical = svc.get_canonical_entity(
        "NYU College of Dentistry", "School",
    )

    assert isinstance(canonical, CanonicalEntity)
    assert canonical.canonical_id == "school:nyu"
    assert canonical.canonical_name == "NYU College of Dentistry"
    assert canonical.source_tier == "L1"
    assert canonical.rank == "preferred"
    assert canonical.match_confidence == pytest.approx(1.0)
    svc._graph.close()


def test_get_canonical_entity_fuzzy_match(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    _seed_graph(svc)

    canonical = svc.get_canonical_entity("Harvard School Dental Medicine", "School")

    assert canonical is not None
    assert canonical.canonical_id == "school:harvard"
    assert canonical.match_confidence >= 0.85
    svc._graph.close()


def test_get_canonical_entity_returns_none_for_unmatched(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    _seed_graph(svc)

    assert svc.get_canonical_entity("Totally Different University", "School") is None
    svc._graph.close()


def test_citation_traceability_threshold(tmp_path: Path) -> None:
    """Slice acceptance NFR-4: ≥99% of results carry references."""

    svc = _make_service(tmp_path)
    _seed_graph(svc)

    results = svc.query_graph("nyu", traversal_depth=3, limit=50)
    with_refs = sum(1 for r in results if r.references)
    rate = with_refs / len(results) if results else 1.0
    assert rate >= 0.99
    svc._graph.close()
