"""`validate_feature_packet(feature)` — checklist for a feature packet's expected files + sections."""

from __future__ import annotations

from dataclasses import dataclass

from tools.graphrag.store.client import NodeQuery
from tools.graphrag.store.sqlite_client import SQLiteGraphClient
from tools.graphrag.types import NodeType

# All files we expect in a normal feature packet (TEMPLATE has more; not all are required).
_EXPECTED_FILES: tuple[str, ...] = (
    "README.md",
    "context.md",
    "requirements.md",
    "plan.md",
    "test-plan.md",
)

_RECOMMENDED_FILES: tuple[str, ...] = (
    "api.md",
    "data.md",
    "state-machine.md",
    "decisions.md",
    "known-issues.md",
    "changelog.md",
)


@dataclass(frozen=True)
class ValidationResult:
    feature_id: str
    slug: str
    expected_files: list[str]
    present_files: list[str]
    missing_files: list[str]
    recommended_missing: list[str]
    warnings: list[str]
    passes: bool


def validate_feature_packet(store: SQLiteGraphClient, feature: str) -> ValidationResult | None:
    slug = feature.removeprefix("feature:") if feature.startswith("feature:") else feature
    feature_node = store.get_node(f"feature:{slug}")
    if feature_node is None:
        return None

    prefix = f"docs/05-features/{slug}/"
    pages = store.query_nodes(NodeQuery(node_type=NodeType.DOC_PAGE, source_path_prefix=prefix))
    present_names = {(p.source_path or "").removeprefix(prefix) for p in pages}

    missing = [f for f in _EXPECTED_FILES if f not in present_names]
    recommended_missing = [f for f in _RECOMMENDED_FILES if f not in present_names]

    warnings: list[str] = []
    if missing:
        warnings.append(f"missing required files: {', '.join(missing)}")
    if recommended_missing:
        warnings.append(f"missing recommended files: {', '.join(recommended_missing)}")

    return ValidationResult(
        feature_id=feature_node.id,
        slug=slug,
        expected_files=list(_EXPECTED_FILES),
        present_files=sorted(present_names),
        missing_files=missing,
        recommended_missing=recommended_missing,
        warnings=warnings,
        passes=len(missing) == 0,
    )
