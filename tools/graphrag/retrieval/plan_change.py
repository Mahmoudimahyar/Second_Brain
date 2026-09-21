"""`plan_change(request, ...)` — text-search + cluster-by-feature suggestion."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from tools.graphrag.retrieval.explain_feature import explain_feature
from tools.graphrag.retrieval.search_codebase import search_codebase
from tools.graphrag.store.sqlite_client import SQLiteGraphClient
from tools.graphrag.types import NodeType


@dataclass(frozen=True)
class SelectedFeature:
    feature_id: str
    slug: str
    name: str
    relevance_score: float
    summary: str
    code_files: list[str]
    tests_to_run: list[str]
    risks: list[str]


@dataclass(frozen=True)
class PlanChange:
    selected_features: list[SelectedFeature]
    suggested_implementation_order: list[str]
    snapshot_notes: str


def plan_change(
    store: SQLiteGraphClient,
    request: str,
    *,
    k_features: int = 3,
) -> PlanChange:
    """Search-then-cluster: find the top features touched by the request."""

    hits = search_codebase(store, request, limit=40)
    # Score features by hit count among their contents.
    feature_scores: Counter[str] = Counter()
    feature_score_sums: dict[str, float] = {}
    for hit in hits:
        slug = _feature_slug_for_node(store, hit.node_id)
        if slug is None:
            continue
        feature_scores[slug] += 1
        feature_score_sums[slug] = feature_score_sums.get(slug, 0.0) + (1.0 / (abs(hit.score) + 1.0))

    top_slugs = [slug for slug, _ in feature_scores.most_common(k_features)]
    selected: list[SelectedFeature] = []
    for slug in top_slugs:
        ex = explain_feature(store, slug, max_per_section=8)
        if ex is None:
            continue
        selected.append(
            SelectedFeature(
                feature_id=ex.feature_id,
                slug=ex.slug,
                name=ex.name,
                relevance_score=feature_score_sums.get(slug, 0.0),
                summary=ex.readme_summary,
                code_files=list(ex.code_files),
                tests_to_run=[t.qualified_name for t in ex.tests],
                risks=[ki.description for ki in ex.known_issues],
            )
        )

    return PlanChange(
        selected_features=selected,
        suggested_implementation_order=[s.slug for s in selected],
        snapshot_notes=f"hits={len(hits)} candidate-slugs={len(feature_scores)}",
    )


def _feature_slug_for_node(store: SQLiteGraphClient, node_id: str) -> str | None:
    node = store.get_node(node_id)
    if node is None:
        return None
    if node.node_type == NodeType.FEATURE:
        slug = node.properties.get("slug")
        return slug if isinstance(slug, str) else None
    # Requirement / AC / KI carry feature_slug explicitly.
    slug = node.properties.get("feature_slug")
    if isinstance(slug, str):
        return slug
    # DocPages under docs/05-features/<slug>/.
    if node.source_path and node.source_path.startswith("docs/05-features/"):
        parts = node.source_path.split("/")
        if len(parts) >= 3:
            return parts[2]
    return None
