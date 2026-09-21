"""Tests for `tools/graphrag/parsers/feature_packet.py`."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.graphrag.parsers import feature_packet
from tools.graphrag.parsers.base import accepts_path
from tools.graphrag.types import NodeType

pytestmark = pytest.mark.unit


# ---------- ACCEPTS pattern ----------


class _StubParser:
    ACCEPTS = feature_packet.ACCEPTS

    def parse(self, file_path, repo_root):  # pragma: no cover - protocol stub
        return None


def test_accepts_slice_readme_requirements_testplan() -> None:
    p = _StubParser()
    assert accepts_path(p, "docs/05-features/01-slice/README.md")
    assert accepts_path(p, "docs/05-features/01-slice/requirements.md")
    assert accepts_path(p, "docs/05-features/01-slice/test-plan.md")


def test_rejects_unrelated_paths() -> None:
    p = _StubParser()
    assert not accepts_path(p, "docs/01-core/product-vision.md")
    assert not accepts_path(p, "docs/05-features/01-slice/plan.md")
    assert not accepts_path(p, "docs/05-features/01-slice/data.md")
    assert not accepts_path(p, "docs/05-features/sub/dir/README.md")
    assert not accepts_path(p, "src/extraction/cascade.py")


# ---------- Feature node ----------


def _slice_path(tmp_repo: Path, slug: str = "01-test-slice") -> Path:
    feature_dir = tmp_repo / "docs" / "05-features" / slug
    feature_dir.mkdir(parents=True)
    return feature_dir


def test_emits_feature_from_readme(tmp_repo: Path) -> None:
    slice_dir = _slice_path(tmp_repo)
    (slice_dir / "README.md").write_text(
        "# Feature: My Test Slice\n\n"
        "**Status:** Spec only. Blocked on something.\n\n"
        "Body.\n",
        encoding="utf-8",
    )

    result = feature_packet.parse(slice_dir / "README.md", tmp_repo)

    feature_nodes = [n for n in result.nodes if n.node_type == NodeType.FEATURE]
    assert len(feature_nodes) == 1
    feature = feature_nodes[0]
    assert feature.id == "feature:01-test-slice"
    assert feature.properties["slug"] == "01-test-slice"
    assert feature.properties["name"] == "My Test Slice"
    assert feature.properties["status"] == "proposed"


def test_template_directory_is_excluded(tmp_repo: Path) -> None:
    template_dir = tmp_repo / "docs" / "05-features" / "TEMPLATE"
    template_dir.mkdir(parents=True)
    (template_dir / "README.md").write_text("# Feature: TEMPLATE\n", encoding="utf-8")

    result = feature_packet.parse(template_dir / "README.md", tmp_repo)

    assert result.nodes == []
    assert result.edges == []


def test_status_normalization_handles_multiple_phrasings(tmp_repo: Path) -> None:
    cases = [
        ("**Status:** Spec only. blah", "proposed"),
        ("**Status:** Proposed — awaiting", "proposed"),
        ("**Status:** In Progress.", "in-progress"),
        ("**Status:** Accepted.", "complete"),
        ("**Status:** Complete.", "complete"),
        ("**Status:** Deferred to V2.", "deferred"),
        ("**Status:** weird made up phrase.", "proposed"),
    ]
    for i, (line, expected) in enumerate(cases):
        slice_dir = _slice_path(tmp_repo, slug=f"01-status-case-{i:02d}")
        (slice_dir / "README.md").write_text(f"# Feature: X\n\n{line}\n", encoding="utf-8")
        result = feature_packet.parse(slice_dir / "README.md", tmp_repo)
        feature = next(n for n in result.nodes if n.node_type == NodeType.FEATURE)
        assert feature.properties["status"] == expected, f"{line!r} → expected {expected}, got {feature.properties['status']}"


def test_h1_without_feature_prefix_still_extracted(tmp_repo: Path) -> None:
    slice_dir = _slice_path(tmp_repo)
    (slice_dir / "README.md").write_text("# Just A Title\n\nbody\n", encoding="utf-8")

    result = feature_packet.parse(slice_dir / "README.md", tmp_repo)

    feature = next(n for n in result.nodes if n.node_type == NodeType.FEATURE)
    assert feature.properties["name"] == "Just A Title"


def test_feature_name_falls_back_to_slug_when_no_h1(tmp_repo: Path) -> None:
    slice_dir = _slice_path(tmp_repo, slug="42-no-h1")
    (slice_dir / "README.md").write_text("No heading here.\n", encoding="utf-8")

    result = feature_packet.parse(slice_dir / "README.md", tmp_repo)

    feature = next(n for n in result.nodes if n.node_type == NodeType.FEATURE)
    assert feature.properties["name"] == "42-no-h1"


# ---------- Requirement nodes ----------


def test_extracts_fr_subitems(tmp_repo: Path) -> None:
    slice_dir = _slice_path(tmp_repo)
    (slice_dir / "requirements.md").write_text(
        "## Functional requirements\n\n"
        "### FR-1 — Ingestion plane\n\n"
        "- **FR-1.1** The system exposes an MCP tool `register_dump(...)`.\n"
        "- **FR-1.2** The L1 Excel adapter accepts ADEA files.\n\n"
        "### FR-2 — Cascade extraction\n\n"
        "- **FR-2.1** Stage 1 filter runs.\n",
        encoding="utf-8",
    )

    result = feature_packet.parse(slice_dir / "requirements.md", tmp_repo)

    reqs = [n for n in result.nodes if n.node_type == NodeType.REQUIREMENT]
    ids = sorted(n.properties["req_id"] for n in reqs)
    assert ids == ["FR-1.1", "FR-1.2", "FR-2.1"]
    fr11 = next(n for n in reqs if n.properties["req_id"] == "FR-1.1")
    assert fr11.properties["kind"] == "functional"
    assert fr11.properties["feature_slug"] == "01-test-slice"
    assert "register_dump" in fr11.properties["description"]


def test_extracts_nfr_with_inline_title(tmp_repo: Path) -> None:
    slice_dir = _slice_path(tmp_repo)
    (slice_dir / "requirements.md").write_text(
        "## Non-functional requirements\n\n"
        "- **NFR-1 Latency**: `query_graph` p95 < 250 ms.\n"
        "- **NFR-2 Cost**: V1 slice extraction sweep ≤ **$25** API spend.\n",
        encoding="utf-8",
    )

    result = feature_packet.parse(slice_dir / "requirements.md", tmp_repo)

    nfrs = [
        n for n in result.nodes
        if n.node_type == NodeType.REQUIREMENT and n.properties["req_id"].startswith("NFR")
    ]
    ids = sorted(n.properties["req_id"] for n in nfrs)
    assert ids == ["NFR-1", "NFR-2"]
    n1 = next(n for n in nfrs if n.properties["req_id"] == "NFR-1")
    assert n1.properties["kind"] == "non-functional"
    assert n1.properties["title"] == "Latency"
    assert "p95" in n1.properties["description"]


def test_duplicate_requirement_id_warned(tmp_repo: Path) -> None:
    slice_dir = _slice_path(tmp_repo)
    (slice_dir / "requirements.md").write_text(
        "- **FR-1.1** First.\n"
        "- **FR-1.1** Second (dupe).\n",
        encoding="utf-8",
    )

    result = feature_packet.parse(slice_dir / "requirements.md", tmp_repo)

    reqs = [n for n in result.nodes if n.node_type == NodeType.REQUIREMENT]
    assert len(reqs) == 1
    assert any("duplicate requirement id" in w for w in result.warnings)


# ---------- AcceptanceCriterion nodes ----------


def test_extracts_ac_headings_with_linked_fr(tmp_repo: Path) -> None:
    slice_dir = _slice_path(tmp_repo)
    (slice_dir / "test-plan.md").write_text(
        "## Acceptance-criteria → test mapping\n\n"
        "### AC-1 — `register_dump` idempotency (FR-1.1)\n\n"
        "- Unit test bla.\n\n"
        "### AC-2 — L1 ingest counts (FR-1.2)\n\n"
        "- Integration test bla.\n\n"
        "### AC-3 — Alias resolution F1 (FR-2.1, FR-3.5, NFR-4)\n\n"
        "- Eval bla.\n",
        encoding="utf-8",
    )

    result = feature_packet.parse(slice_dir / "test-plan.md", tmp_repo)

    acs = [n for n in result.nodes if n.node_type == NodeType.ACCEPTANCE_CRITERION]
    ids = sorted(n.properties["ac_id"] for n in acs)
    assert ids == ["AC-1", "AC-2", "AC-3"]
    ac3 = next(n for n in acs if n.properties["ac_id"] == "AC-3")
    assert ac3.properties["linked_requirement_ids"] == ["FR-2.1", "FR-3.5", "NFR-4"]
    assert ac3.properties["feature_slug"] == "01-test-slice"
    assert "Alias resolution F1" in ac3.properties["title"]


def test_ac_without_linked_fr_still_extracted(tmp_repo: Path) -> None:
    slice_dir = _slice_path(tmp_repo)
    (slice_dir / "test-plan.md").write_text(
        "### AC-5 — Citation traceability\n\n- bla.\n",
        encoding="utf-8",
    )

    result = feature_packet.parse(slice_dir / "test-plan.md", tmp_repo)

    acs = [n for n in result.nodes if n.node_type == NodeType.ACCEPTANCE_CRITERION]
    assert len(acs) == 1
    assert acs[0].properties["linked_requirement_ids"] == []


# ---------- Dispatch behavior ----------


def test_parsing_unrelated_file_returns_empty_result(tmp_repo: Path) -> None:
    other = tmp_repo / "docs" / "01-core" / "product-vision.md"
    other.parent.mkdir(parents=True)
    other.write_text("# Vision\n\nbody\n", encoding="utf-8")

    result = feature_packet.parse(other, tmp_repo)

    assert result.nodes == []
    assert result.edges == []


def test_parsing_plan_md_in_slice_dir_returns_empty(tmp_repo: Path) -> None:
    """Slice dir has plan.md, data.md, etc. — parser should ignore those."""

    slice_dir = _slice_path(tmp_repo)
    (slice_dir / "plan.md").write_text("# Plan\n", encoding="utf-8")

    result = feature_packet.parse(slice_dir / "plan.md", tmp_repo)

    assert result.nodes == []
    assert result.edges == []


# ---------- Idempotency ----------


def test_parser_is_deterministic(tmp_repo: Path) -> None:
    slice_dir = _slice_path(tmp_repo)
    (slice_dir / "requirements.md").write_text(
        "- **FR-1.1** First.\n- **NFR-1 Latency**: fast.\n",
        encoding="utf-8",
    )

    a = feature_packet.parse(slice_dir / "requirements.md", tmp_repo)
    b = feature_packet.parse(slice_dir / "requirements.md", tmp_repo)
    assert [(n.id, n.content_hash) for n in a.nodes] == [
        (n.id, n.content_hash) for n in b.nodes
    ]
