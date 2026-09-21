"""`explain_feature(feature, ...)` — aggregated Feature view: README + Reqs + ACs + Code + Tests + ADRs + KI."""

from __future__ import annotations

from dataclasses import dataclass

from tools.graphrag.store.client import EdgeQuery, NodeQuery
from tools.graphrag.store.sqlite_client import SQLiteGraphClient
from tools.graphrag.types import EdgeType, Node, NodeType


@dataclass(frozen=True)
class RequirementBrief:
    req_id: str
    title: str
    description: str
    kind: str


@dataclass(frozen=True)
class AcceptanceCriterionBrief:
    ac_id: str
    description: str
    linked_req_ids: list[str]


@dataclass(frozen=True)
class TestBrief:
    qualified_name: str
    source_path: str | None
    linked_req_ids: list[str]
    linked_ac_ids: list[str]


@dataclass(frozen=True)
class ADRBrief:
    adr_id: str
    title: str
    status: str
    decision_summary: str


@dataclass(frozen=True)
class KnownIssueBrief:
    ki_id: str
    severity: str
    description: str


@dataclass(frozen=True)
class FeatureExplanation:
    feature_id: str
    slug: str
    name: str
    status: str
    readme_summary: str
    requirements: list[RequirementBrief]
    acceptance_criteria: list[AcceptanceCriterionBrief]
    code_files: list[str]
    tests: list[TestBrief]
    adrs: list[ADRBrief]
    known_issues: list[KnownIssueBrief]


def _slug_from_feature_arg(feature: str) -> str:
    return feature.removeprefix("feature:") if feature.startswith("feature:") else feature


def explain_feature(
    store: SQLiteGraphClient,
    feature: str,
    *,
    max_per_section: int = 15,
) -> FeatureExplanation | None:
    slug = _slug_from_feature_arg(feature)
    feature_node = store.get_node(f"feature:{slug}")
    if feature_node is None:
        return None

    readme_summary = _readme_summary(store, slug)
    requirements = _requirements_for(store, feature_node.id, max_per_section)
    acceptance_criteria = _acs_for_requirements(store, [r.req_id for r in requirements], slug, max_per_section)
    code_files = _code_files_for_feature(store, feature_node.id, max_per_section)
    tests = _tests_for_feature(store, [r.req_id for r in requirements], [a.ac_id for a in acceptance_criteria], max_per_section)
    adrs = _adrs_for_code(store, code_files, max_per_section)
    known_issues = _known_issues_for_feature(store, feature_node.id, max_per_section)

    name_prop = feature_node.properties.get("name")
    status_prop = feature_node.properties.get("status")
    return FeatureExplanation(
        feature_id=feature_node.id,
        slug=slug,
        name=name_prop if isinstance(name_prop, str) else slug,
        status=status_prop if isinstance(status_prop, str) else "proposed",
        readme_summary=readme_summary,
        requirements=requirements,
        acceptance_criteria=acceptance_criteria,
        code_files=code_files,
        tests=tests,
        adrs=adrs,
        known_issues=known_issues,
    )


def _readme_summary(store: SQLiteGraphClient, slug: str) -> str:
    page = store.get_node(f"doc:docs:05-features:{slug}:README.md")
    if page is None or page.source_path is None:
        return ""
    sections = store.query_nodes(
        NodeQuery(node_type=NodeType.DOC_SECTION, source_path_prefix=page.source_path + "#")
    )
    # Use the section under the first H1 if it exists; else any content.
    h1_text = ""
    for s in sections:
        level = s.properties.get("level")
        text = s.properties.get("text")
        if level == 1 and isinstance(text, str):
            h1_text = text
            break
    if not h1_text and sections:
        t = sections[0].properties.get("text")
        if isinstance(t, str):
            h1_text = t
    return h1_text[:600]


def _requirements_for(store: SQLiteGraphClient, feature_id: str, limit: int) -> list[RequirementBrief]:
    edges = store.query_edges(EdgeQuery(edge_type=EdgeType.FEATURE_HAS_REQUIREMENT, from_node_id=feature_id))
    out: list[RequirementBrief] = []
    for edge in edges[:limit]:
        node = store.get_node(edge.to_node_id)
        if node is None:
            continue
        out.append(
            RequirementBrief(
                req_id=str(node.properties.get("req_id") or ""),
                title=str(node.properties.get("title") or ""),
                description=str(node.properties.get("description") or ""),
                kind=str(node.properties.get("kind") or "functional"),
            )
        )
    return out


def _acs_for_requirements(
    store: SQLiteGraphClient,
    req_ids: list[str],
    slug: str,
    limit: int,
) -> list[AcceptanceCriterionBrief]:
    """Return ACs linked to any of `req_ids` (within the feature's slug)."""

    edges = store.query_edges(EdgeQuery(edge_type=EdgeType.REQUIREMENT_HAS_ACCEPTANCE_CRITERION))
    req_id_set = set(req_ids)
    seen: set[str] = set()
    out: list[AcceptanceCriterionBrief] = []
    for edge in edges:
        # Only edges whose source Requirement belongs to this feature.
        from_node = store.get_node(edge.from_node_id)
        if from_node is None:
            continue
        from_req_id = str(from_node.properties.get("req_id") or "")
        if from_req_id not in req_id_set:
            continue
        ac_node = store.get_node(edge.to_node_id)
        if ac_node is None or ac_node.id in seen:
            continue
        seen.add(ac_node.id)
        linked = ac_node.properties.get("linked_requirement_ids", [])
        out.append(
            AcceptanceCriterionBrief(
                ac_id=str(ac_node.properties.get("ac_id") or ""),
                description=str(ac_node.properties.get("description") or "")[:400],
                linked_req_ids=[str(x) for x in linked if isinstance(x, str)],
            )
        )
        if len(out) >= limit:
            break
    return out


def _code_files_for_feature(store: SQLiteGraphClient, feature_id: str, limit: int) -> list[str]:
    edges = store.query_edges(EdgeQuery(edge_type=EdgeType.FEATURE_IMPLEMENTED_BY, from_node_id=feature_id))
    paths: list[str] = []
    for edge in edges[:limit]:
        node = store.get_node(edge.to_node_id)
        if node is None or node.source_path is None:
            continue
        paths.append(node.source_path)
    return paths


def _tests_for_feature(
    store: SQLiteGraphClient,
    req_ids: list[str],
    ac_ids: list[str],
    limit: int,
) -> list[TestBrief]:
    """Pull all tests whose linked_req_ids ∩ req_ids or linked_ac_ids ∩ ac_ids is non-empty."""

    seen: set[str] = set()
    out: list[TestBrief] = []
    req_set = set(req_ids)
    ac_set = set(ac_ids)
    for case in store.query_nodes(NodeQuery(node_type=NodeType.TEST_CASE)):
        linked_reqs = [r for r in (case.properties.get("linked_req_ids") or []) if isinstance(r, str)]
        linked_acs = [a for a in (case.properties.get("linked_ac_ids") or []) if isinstance(a, str)]
        if req_set.isdisjoint(linked_reqs) and ac_set.isdisjoint(linked_acs):
            continue
        if case.id in seen:
            continue
        seen.add(case.id)
        out.append(
            TestBrief(
                qualified_name=str(case.properties.get("qualified_name") or case.id),
                source_path=case.source_path,
                linked_req_ids=linked_reqs,
                linked_ac_ids=linked_acs,
            )
        )
        if len(out) >= limit:
            break
    return out


def _adrs_for_code(store: SQLiteGraphClient, code_files: list[str], limit: int) -> list[ADRBrief]:
    if not code_files:
        return []
    seen: set[str] = set()
    out: list[ADRBrief] = []
    code_ids = {f"code:{p}" for p in code_files}
    edges = store.query_edges(EdgeQuery(edge_type=EdgeType.ADR_DECIDES))
    for edge in edges:
        if edge.to_node_id not in code_ids:
            continue
        adr = store.get_node(edge.from_node_id)
        if adr is None or adr.id in seen:
            continue
        seen.add(adr.id)
        out.append(_adr_brief(adr))
        if len(out) >= limit:
            break
    return out


def _adr_brief(node: Node) -> ADRBrief:
    return ADRBrief(
        adr_id=str(node.properties.get("adr_id") or ""),
        title=str(node.properties.get("title") or ""),
        status=str(node.properties.get("status") or "proposed"),
        decision_summary=str(node.properties.get("decision_summary") or "")[:400],
    )


def _known_issues_for_feature(store: SQLiteGraphClient, feature_id: str, limit: int) -> list[KnownIssueBrief]:
    edges = store.query_edges(EdgeQuery(edge_type=EdgeType.KNOWN_ISSUE_AFFECTS, to_node_id=feature_id))
    out: list[KnownIssueBrief] = []
    for edge in edges[:limit]:
        ki = store.get_node(edge.from_node_id)
        if ki is None:
            continue
        out.append(
            KnownIssueBrief(
                ki_id=str(ki.properties.get("ki_id") or ""),
                severity=str(ki.properties.get("severity") or "med"),
                description=str(ki.properties.get("description") or "")[:400],
            )
        )
    return out
