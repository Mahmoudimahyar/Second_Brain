"""Sample schema used by every candidate engine.

Plain dataclasses (not Pydantic) for speed during bulk-load. Every edge carries the V1 property
convention: source_tier, rank, references, qualifiers, bitemporal 4-tuple, created_utc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SampleNode:
    id: str
    label: str
    source_tier: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class SampleEdge:
    id: str
    relation: str
    from_id: str
    to_id: str
    source_tier: str
    rank: str
    references: list[str] = field(default_factory=list)
    qualifiers: dict[str, Any] = field(default_factory=dict)
    t_valid_from: datetime | None = None
    t_valid_to: datetime | None = None
    t_ingest_from: datetime | None = None
    t_ingest_to: datetime | None = None
    created_utc: datetime | None = None
    confidence: float = 1.0


@dataclass
class SampleEmbedding:
    """384-d synthetic vector for HNSW recall testing.

    Synthetic vectors mean recall@10 measures the index's ANN approximation, not embedding
    quality. That's correct for a bake-off: we're picking the engine, not the embedder.
    """

    chunk_id: str
    vector: list[float]


@dataclass
class Sample:
    nodes: list[SampleNode]
    edges: list[SampleEdge]
    embeddings: list[SampleEmbedding]
    query_vectors: list[SampleEmbedding]
    ground_truth_top10: dict[str, list[str]]  # query_id → list of top-10 chunk_ids
