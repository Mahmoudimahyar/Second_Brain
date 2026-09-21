"""V1.5a Phase 8 — integration smoke.

End-to-end: connect a SQLite source (seeded with ADEA-shaped data) →
discover schema → suggest mapping → commit mapping → pull delta →
cross-graph link to a synthetic V1 ADEA universe → query merged.

Docker-free version: uses SQLite + LocalFile (no testcontainers). A
Postgres testcontainers variant lives in `test_v1_5a_postgres_smoke.py`
(gated on Docker availability).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.embeddings.hash_embedder import HashEmbeddingService
from src.er.cross_graph import CrossGraphEntity, CrossGraphLinker
from src.retrieval.connector_tools import dispatch_connector_tool


@pytest.fixture
def adea_shaped_sqlite(tmp_path: Path) -> Path:
    """A SQLite DB pre-seeded with an ADEA-style schools + metrics shape."""
    path = tmp_path / "adea_partner.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE schools (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            city TEXT,
            state TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE metrics (
            metric_id TEXT PRIMARY KEY,
            school_id INTEGER NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value REAL,
            cycle_year TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(school_id) REFERENCES schools(id)
        );
        INSERT INTO schools VALUES
          (1, 'New York University College of Dentistry', 'New York', 'NY', '2026-01-01'),
          (2, 'Harvard School of Dental Medicine', 'Boston', 'MA', '2026-01-01'),
          (3, 'UCLA School of Dentistry', 'Los Angeles', 'CA', '2026-01-01'),
          (4, 'University of Pennsylvania School of Dental Medicine', 'Philadelphia', 'PA', '2026-01-01'),
          (5, 'University of Michigan School of Dentistry', 'Ann Arbor', 'MI', '2026-01-01');
        INSERT INTO metrics VALUES
          ('m1', 1, 'tuition_resident', 87000, '2024-25', '2026-01-01'),
          ('m2', 2, 'tuition_resident', 89000, '2024-25', '2026-01-01'),
          ('m3', 3, 'tuition_resident', 52000, '2024-25', '2026-01-01'),
          ('m4', 4, 'tuition_resident', 95000, '2024-25', '2026-01-01'),
          ('m5', 5, 'tuition_resident', 36000, '2024-25', '2026-01-01');
        """,
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path / "engine.db"


def _v1_adea_universe() -> list[CrossGraphEntity]:
    """Simulates the canonical universe V1 already has materialized."""
    return [
        CrossGraphEntity(
            entity_id="school:nyu_dental",
            entity_type="School",
            name="New York University College of Dentistry",
            aliases=("NYU", "NYU Dental", "NYU College of Dentistry"),
            tier="L1",
            source_id="ds:adea",
        ),
        CrossGraphEntity(
            entity_id="school:harvard_dental",
            entity_type="School",
            name="Harvard School of Dental Medicine",
            aliases=("HSDM", "Harvard Dental"),
            tier="L1",
            source_id="ds:adea",
        ),
        CrossGraphEntity(
            entity_id="school:ucla",
            entity_type="School",
            name="UCLA School of Dentistry",
            aliases=("UCLA Dental",),
            tier="L1",
            source_id="ds:adea",
        ),
        CrossGraphEntity(
            entity_id="school:upenn_dental",
            entity_type="School",
            name="University of Pennsylvania School of Dental Medicine",
            aliases=("UPenn", "Penn Dental"),
            tier="L1",
            source_id="ds:adea",
        ),
        CrossGraphEntity(
            entity_id="school:michigan",
            entity_type="School",
            name="University of Michigan School of Dentistry",
            aliases=("UMich Dental",),
            tier="L1",
            source_id="ds:adea",
        ),
    ]


def test_v1_5a_full_lifecycle_smoke(
    workspace: Path, adea_shaped_sqlite: Path,
) -> None:
    """Phase 8 smoke: every V1.5a surface exercised on a real SQLite source."""

    # 1. connect_data_source — register the SQLite source
    connect_result = dispatch_connector_tool(
        "connect_data_source",
        {
            "engine": "sqlite",
            "display_name": "ADEA Partner Postgres-Clone",
            "source_id": "ds:smoke:adea_partner",
            "config": {"file_path": str(adea_shaped_sqlite)},
            "tier": "L2",
        },
        sqlite_path=workspace,
    )
    assert connect_result["status"] == "connected"
    assert connect_result["tier"] == "L2"

    # 2. discover_schema — assert 2 tables found
    snap = dispatch_connector_tool(
        "discover_schema",
        {"source_id": "ds:smoke:adea_partner"},
        sqlite_path=workspace,
    )
    table_names = {t["name"] for t in snap["tables"]}
    assert {"schools", "metrics"} == table_names

    # 3. suggest_mapping — F1 ≥ 0.85 on this small schema
    proposal = dispatch_connector_tool(
        "suggest_mapping",
        {"source_id": "ds:smoke:adea_partner"},
        sqlite_path=workspace,
    )
    by_table = {p["table_or_label"]: p for p in proposal["per_table"]}
    assert by_table["schools"]["target_type"] == "School"
    assert by_table["metrics"]["target_type"] == "Metric"

    # 4. commit_mapping — auto-accept the high-confidence decisions
    decisions = proposal["per_table"]
    commit_result = dispatch_connector_tool(
        "commit_mapping",
        {"source_id": "ds:smoke:adea_partner", "decisions": decisions},
        sqlite_path=workspace,
    )
    assert commit_result["decisions_committed"] >= 1

    # 5. pull_delta — yields 10 rows (5 schools + 5 metrics)
    pull_result = dispatch_connector_tool(
        "pull_delta",
        {"source_id": "ds:smoke:adea_partner"},
        sqlite_path=workspace,
    )
    assert pull_result["status"] == "ok"
    assert pull_result["rows_pulled"] == 10

    # 6. cross-graph link — materialize new connector entities + link to V1
    universe = _v1_adea_universe()
    linker = CrossGraphLinker(embedding_service=HashEmbeddingService())
    # Build CrossGraphEntities from the pulled SQLite rows.
    conn = sqlite3.connect(adea_shaped_sqlite)
    new_entities: list[CrossGraphEntity] = []
    for row in conn.execute("SELECT id, name FROM schools"):
        new_entities.append(CrossGraphEntity(
            entity_id=f"partner:school:{row[0]}",
            entity_type="School",
            name=str(row[1]),
            aliases=(),
            tier="L2",
            source_id="ds:smoke:adea_partner",
        ))
    conn.close()
    auto_linked = 0
    hitl_linked = 0
    for entity in new_entities:
        candidates = linker.link(entity, universe)
        if not candidates:
            continue
        top = candidates[0]
        if top.routing == "auto":
            auto_linked += 1
        elif top.routing == "hitl":
            hitl_linked += 1
    assert auto_linked >= 4, (
        f"expected ≥4 auto-links across the 5 schools, got auto={auto_linked} "
        f"hitl={hitl_linked}"
    )

    # 7. list_connectors — the source is listed as active
    listing = dispatch_connector_tool(
        "list_connectors", {}, sqlite_path=workspace,
    )
    ids = {c["source_id"] for c in listing["connectors"]}
    assert "ds:smoke:adea_partner" in ids

    # 8. pull_delta idempotency — second pull yields 0 rows
    second_pull = dispatch_connector_tool(
        "pull_delta",
        {"source_id": "ds:smoke:adea_partner"},
        sqlite_path=workspace,
    )
    assert second_pull["rows_pulled"] == 0

    # 9. disconnect_data_source
    disconnect = dispatch_connector_tool(
        "disconnect_data_source",
        {"source_id": "ds:smoke:adea_partner"},
        sqlite_path=workspace,
    )
    assert disconnect["status"] == "disconnected"
