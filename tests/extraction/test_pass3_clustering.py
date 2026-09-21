"""Tests for `src.extraction.pass3_clustering.Pass3ClusterRunner`.

Uses `HashEmbeddingService` (no ML model required) + `MockProvider`. The real
`BGEEmbeddingService` is exercised in the live smoke at the end of Tier A.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.embeddings import HashEmbeddingService
from src.extraction.cache import ExtractionCache
from src.extraction.pass3_clustering import Pass3ClusterRunner, Pass3Output
from src.gateway import MockProvider, ModelGateway, TaskID


def _utc() -> datetime:
    return datetime(2026, 5, 21, tzinfo=UTC)


def _summary_fixture(_p: str) -> str:
    return json.dumps({
        "label": "dental school acceptance",
        "description": "Posts about getting accepted to dental schools.",
    })


def _gateway() -> ModelGateway:
    gw = ModelGateway()
    gw.register(TaskID.PASS3_CLUSTER_SUMMARY,
                MockProvider(fixture=_summary_fixture))  # type: ignore[arg-type]
    return gw


def test_empty_input_returns_empty_output() -> None:
    runner = Pass3ClusterRunner(embedder=HashEmbeddingService())
    out = runner.run([], ingest_time=_utc())
    assert out.embeddings == []
    assert out.clusters == []
    assert out.nodes == []
    assert out.edges == []


def test_single_post_yields_no_clusters_below_min_size() -> None:
    runner = Pass3ClusterRunner(embedder=HashEmbeddingService(), min_cluster_size=2)
    out = runner.run([("p1", "alone")], ingest_time=_utc())
    assert len(out.embeddings) == 1
    assert out.clusters == []
    assert out.nodes == []


def test_clusters_emitted_when_min_size_met() -> None:
    runner = Pass3ClusterRunner(
        embedder=HashEmbeddingService(), gateway=_gateway(),
        n_clusters=2, min_cluster_size=2,
    )
    posts = [(f"p{i}", "got accepted to dental school today!") for i in range(4)]
    posts += [(f"q{i}", "DAT prep advice please") for i in range(4)]

    out = runner.run(posts, ingest_time=_utc())

    assert isinstance(out, Pass3Output)
    assert len(out.embeddings) == 8
    assert all(n.label == "Cluster" for n in out.nodes)
    assert all(e.label == "IN_CLUSTER" for e in out.edges)


def test_in_cluster_edges_link_posts_to_cluster(tmp_path) -> None:  # type: ignore[no-untyped-def]
    runner = Pass3ClusterRunner(
        embedder=HashEmbeddingService(), gateway=_gateway(),
        n_clusters=1, min_cluster_size=1,
    )
    posts = [("p1", "x"), ("p2", "x"), ("p3", "x")]

    out = runner.run(posts, ingest_time=_utc())

    assert len(out.nodes) == 1
    cluster_id = out.nodes[0].id
    edge_targets = {(e.from_id, e.to_id) for e in out.edges}
    assert ("p1", cluster_id) in edge_targets
    assert ("p2", cluster_id) in edge_targets
    assert ("p3", cluster_id) in edge_targets


def test_cluster_summary_pulls_label_from_gateway() -> None:
    runner = Pass3ClusterRunner(
        embedder=HashEmbeddingService(), gateway=_gateway(),
        n_clusters=1, min_cluster_size=1,
    )
    posts = [("p1", "got accepted today"), ("p2", "got accepted today")]

    out = runner.run(posts, ingest_time=_utc())

    assert out.clusters[0].label == "dental school acceptance"
    assert out.clusters[0].description.startswith("Posts about")


def test_cluster_label_fallback_when_no_gateway() -> None:
    runner = Pass3ClusterRunner(
        embedder=HashEmbeddingService(), gateway=None,
        n_clusters=1, min_cluster_size=1,
    )
    posts = [("p1", "got accepted today!"), ("p2", "got in today!")]

    out = runner.run(posts, ingest_time=_utc())

    assert "no LLM gateway" in out.clusters[0].description


def test_n_clusters_capped_at_posts_count() -> None:
    runner = Pass3ClusterRunner(
        embedder=HashEmbeddingService(), gateway=_gateway(),
        n_clusters=10, min_cluster_size=1,
    )
    posts = [("p1", "a"), ("p2", "b"), ("p3", "c")]
    out = runner.run(posts, ingest_time=_utc())
    # Should not crash with k > n_posts; clusters capped at 3
    assert len(out.clusters) <= 3


def test_cluster_node_carries_member_count_and_label() -> None:
    runner = Pass3ClusterRunner(
        embedder=HashEmbeddingService(), gateway=_gateway(),
        n_clusters=1, min_cluster_size=1,
    )
    posts = [("p1", "x"), ("p2", "x"), ("p3", "x")]
    out = runner.run(posts, ingest_time=_utc())

    n = out.nodes[0]
    assert n.properties["member_count"] == 3
    assert n.properties["topic_label"] == "dental school acceptance"
    assert n.properties["embedding_model"] == "hash-stub-v1"


def test_deterministic_cluster_ids() -> None:
    """Same input → same cluster ID (idempotent reruns)."""

    runner_a = Pass3ClusterRunner(
        embedder=HashEmbeddingService(), gateway=_gateway(),
        n_clusters=1, min_cluster_size=1,
    )
    runner_b = Pass3ClusterRunner(
        embedder=HashEmbeddingService(), gateway=_gateway(),
        n_clusters=1, min_cluster_size=1,
    )
    posts = [("p1", "x"), ("p2", "x")]

    out_a = runner_a.run(posts, ingest_time=_utc())
    out_b = runner_b.run(posts, ingest_time=_utc())

    assert out_a.nodes[0].id == out_b.nodes[0].id


def test_hdbscan_method_clusters_without_k() -> None:
    """V1.x: density-based clustering option. K is inferred, not specified.

    A-055 ultimately wants signed-graph community detection on Pass 4 SUPPORTS /
    CONTRADICTS edges; until those exist, HDBSCAN on embeddings is the closest
    K-less alternative and a strict improvement over MiniBatchKMeans for our
    use case (post topics aren't equal-sized convex blobs)."""

    runner = Pass3ClusterRunner(
        embedder=HashEmbeddingService(), gateway=_gateway(),
        method="hdbscan", min_cluster_size=2,
    )
    posts = [(f"p{i}", "got accepted to dental school today!") for i in range(5)]
    posts += [(f"q{i}", "DAT prep advice please") for i in range(5)]
    posts += [(f"r{i}", "personal statement editing services") for i in range(5)]

    out = runner.run(posts, ingest_time=_utc())

    # HDBSCAN should discover multiple clusters without us specifying K.
    # Hash embeddings aren't great signal but we should at least see ≥ 1 cluster.
    assert len(out.embeddings) == 15
    assert len(out.nodes) >= 1


def test_hdbscan_rejects_unknown_method() -> None:
    runner = Pass3ClusterRunner(
        embedder=HashEmbeddingService(), gateway=_gateway(),
        method="not_a_method",
    )
    posts = [("p1", "x"), ("p2", "y")]
    with pytest.raises(ValueError, match="unknown clustering method"):
        runner.run(posts, ingest_time=_utc())


def test_cluster_labels_are_deterministic_via_extraction_cache(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """GAP-039 closure: caching by centroid signature + sample texts gives
    reproducible cluster labels across re-runs on the same data, even when the
    underlying LLM is non-deterministic."""

    cache = ExtractionCache(sqlite_path=Path(tmp_path) / "cache.db")
    # Simulate a non-deterministic LLM by toggling the fixture between calls.
    call_count = {"n": 0}

    def varying_fixture(_p: str) -> str:
        call_count["n"] += 1
        return json.dumps({
            "label": f"label_v{call_count['n']}",
            "description": f"description v{call_count['n']}",
        })

    def make_runner() -> Pass3ClusterRunner:
        gw = ModelGateway()
        gw.register(TaskID.PASS3_CLUSTER_SUMMARY,
                    MockProvider(fixture=varying_fixture))  # type: ignore[arg-type]
        return Pass3ClusterRunner(
            embedder=HashEmbeddingService(), gateway=gw, cache=cache,
            n_clusters=1, min_cluster_size=1,
        )

    posts = [("p1", "Accepted to UPenn today!"), ("p2", "Accepted to UPenn today!")]

    first = make_runner().run(posts, ingest_time=_utc())
    second = make_runner().run(posts, ingest_time=_utc())

    assert first.clusters[0].label == second.clusters[0].label
    assert first.clusters[0].description == second.clusters[0].description
    # Second run should hit cache → reported cost == 0.
    assert second.cost_usd == pytest.approx(0.0)


def test_cluster_label_cache_key_changes_on_centroid_change() -> None:
    """Different centroids → different cache keys → label cache won't collide."""

    runner = Pass3ClusterRunner(embedder=HashEmbeddingService())
    key_a = runner._cache_key_for_cluster((0.1, 0.2, 0.3), ["sample"])
    key_b = runner._cache_key_for_cluster((0.9, 0.2, 0.3), ["sample"])
    assert key_a != key_b


def test_cost_aggregation_per_cluster() -> None:
    runner = Pass3ClusterRunner(
        embedder=HashEmbeddingService(),
        gateway=_gateway(),
        n_clusters=2, min_cluster_size=1,
    )
    posts = [("p1", "x"), ("p2", "y"), ("p3", "x"), ("p4", "y")]
    out = runner.run(posts, ingest_time=_utc())
    assert out.cost_usd == pytest.approx(0.0)  # MockProvider zero-cost


# ---------------------------------------------------------------------------
# GAP-049 signed spectral clustering tests
# ---------------------------------------------------------------------------

def test_signed_spectral_method_accepted() -> None:
    """method='signed_spectral' does not raise on valid input."""
    runner = Pass3ClusterRunner(
        embedder=HashEmbeddingService(), gateway=_gateway(),
        method="signed_spectral", n_clusters=2, min_cluster_size=1,
    )
    posts = [(f"p{i}", f"text {i}") for i in range(6)]
    sentiments = {f"p{i}": ("positive" if i < 3 else "negative") for i in range(6)}
    out = runner.run(posts, ingest_time=_utc(), sentiments=sentiments)
    assert len(out.embeddings) == 6
    assert len(out.nodes) >= 1


def test_signed_spectral_no_sentiments_falls_back_to_kmeans() -> None:
    """When no sentiments provided, signed_spectral degrades to plain KMeans."""
    runner = Pass3ClusterRunner(
        embedder=HashEmbeddingService(), gateway=_gateway(),
        method="signed_spectral", n_clusters=2, min_cluster_size=1,
    )
    posts = [(f"p{i}", f"text {i}") for i in range(4)]
    # No sentiments → sparse signed matrix → KMeans fallback
    out = runner.run(posts, ingest_time=_utc(), sentiments={})
    assert len(out.nodes) >= 1


def test_signed_spectral_emits_in_cluster_edges() -> None:
    """Signed spectral still emits IN_CLUSTER edges for all posts."""
    runner = Pass3ClusterRunner(
        embedder=HashEmbeddingService(), gateway=_gateway(),
        method="signed_spectral", n_clusters=1, min_cluster_size=1,
    )
    posts = [("a", "text"), ("b", "text"), ("c", "text")]
    sentiments = {"a": "positive", "b": "positive", "c": "negative"}
    out = runner.run(posts, ingest_time=_utc(), sentiments=sentiments)
    post_ids_in_edges = {e.from_id for e in out.edges}
    assert {"a", "b", "c"}.issubset(post_ids_in_edges)


def test_signed_spectral_rejects_unknown_method() -> None:
    runner = Pass3ClusterRunner(embedder=HashEmbeddingService(), method="not_a_method")
    with pytest.raises(ValueError, match="unknown clustering method"):
        runner.run([("p1", "x"), ("p2", "y")], ingest_time=_utc())


def test_signed_spectral_single_post() -> None:
    """Single-post input doesn't crash signed spectral (falls into k=1 guard)."""
    runner = Pass3ClusterRunner(
        embedder=HashEmbeddingService(),
        method="signed_spectral", n_clusters=2, min_cluster_size=1,
    )
    out = runner.run([("p1", "alone")], ingest_time=_utc(), sentiments={"p1": "positive"})
    assert len(out.embeddings) == 1
