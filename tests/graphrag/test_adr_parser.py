"""Tests for `tools/graphrag/parsers/adr.py`."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.graphrag.parsers import adr
from tools.graphrag.parsers.base import accepts_path
from tools.graphrag.types import NodeType

pytestmark = pytest.mark.unit


class _StubParser:
    ACCEPTS = adr.ACCEPTS

    def parse(self, file_path, repo_root):  # pragma: no cover
        return None


def test_accepts_adr_files() -> None:
    p = _StubParser()
    assert accepts_path(p, "docs/11-decisions/ADR-001-graph-db.md")
    assert accepts_path(p, "docs/11-decisions/ADR-011-model-gateway-and-mcp-policy.md")


def test_rejects_non_adr_files() -> None:
    p = _StubParser()
    assert not accepts_path(p, "docs/11-decisions/TEMPLATE.md")
    assert not accepts_path(p, "docs/01-core/product-vision.md")
    assert not accepts_path(p, "docs/05-features/01-slice/README.md")


def _adr_file(tmp_repo: Path, name: str, body: str) -> Path:
    adr_dir = tmp_repo / "docs" / "11-decisions"
    adr_dir.mkdir(parents=True, exist_ok=True)
    p = adr_dir / name
    p.write_text(body, encoding="utf-8")
    return p


def test_emits_one_adr_node(tmp_repo: Path) -> None:
    body = (
        "# ADR-001: Graph Database Selection\n\n"
        "Status: **proposed** — pending bake-off\n"
        "Date: 2026-05-20\n\n"
        "## Context\n\nblah\n\n"
        "## Decision\n\n"
        "**Pending a bake-off** measuring all three candidates.\n\n"
        "Second paragraph.\n\n"
        "## Consequences\n\nblah\n"
    )
    p = _adr_file(tmp_repo, "ADR-001-graph-db.md", body)

    result = adr.parse(p, tmp_repo)

    nodes = [n for n in result.nodes if n.node_type == NodeType.ADR]
    assert len(nodes) == 1
    node = nodes[0]
    assert node.id == "adr:ADR-001"
    assert node.properties["adr_id"] == "ADR-001"
    assert node.properties["status"] == "proposed"
    assert node.properties["date"] == "2026-05-20"
    assert "Pending a bake-off" in node.properties["decision_summary"]
    assert "Second paragraph" not in node.properties["decision_summary"]


def test_status_enum_normalized(tmp_repo: Path) -> None:
    cases = [
        ("Status: **proposed**", "proposed"),
        ("Status: **accepted**", "accepted"),
        ("Status: accepted (R5 revision)", "accepted"),
        ("Status: deprecated", "deprecated"),
        ("Status: pending", "pending"),
        ("Status: tbd", "pending"),
        ("Status: something-weird", "proposed"),
    ]
    for i, (status_line, expected) in enumerate(cases):
        body = f"# ADR-{i + 100}: T\n\n{status_line}\nDate: 2026-05-20\n\n## Decision\n\nx.\n"
        p = _adr_file(tmp_repo, f"ADR-{i + 100}-x.md", body)
        result = adr.parse(p, tmp_repo)
        node = next(n for n in result.nodes if n.node_type == NodeType.ADR)
        assert node.properties["status"] == expected, status_line


def test_missing_date_parses_to_none(tmp_repo: Path) -> None:
    body = (
        "# ADR-005: Title\n\n"
        "Status: **accepted**\n\n"
        "## Decision\n\n"
        "Decided.\n"
    )
    p = _adr_file(tmp_repo, "ADR-005-x.md", body)

    result = adr.parse(p, tmp_repo)
    node = next(n for n in result.nodes if n.node_type == NodeType.ADR)
    assert node.properties["date"] is None


def test_affects_modules_extracted_from_related_code(tmp_repo: Path) -> None:
    body = (
        "# ADR-008: Title\n\n"
        "Status: accepted\nDate: 2026-05-20\n\n"
        "## Decision\n\nDecided.\n\n"
        "## Related code\n\n"
        "- `src/credibility/reddit_rubric.py`\n"
        "- `src/credibility/sdn_rubric.py` — split rubric\n"
        "- `src/conflict/resolver.py` — `prescient_correct` increment path\n"
    )
    p = _adr_file(tmp_repo, "ADR-008-x.md", body)

    result = adr.parse(p, tmp_repo)
    node = next(n for n in result.nodes if n.node_type == NodeType.ADR)
    affects = node.properties["affects_modules"]
    assert "src/credibility/reddit_rubric.py" in affects
    assert "src/credibility/sdn_rubric.py" in affects
    assert "src/conflict/resolver.py" in affects


def test_no_h1_yields_warning_no_node(tmp_repo: Path) -> None:
    body = "Status: accepted\nDate: 2026-05-20\n"
    p = _adr_file(tmp_repo, "ADR-999-no-h1.md", body)

    result = adr.parse(p, tmp_repo)
    assert result.nodes == []
    assert any("no ADR H1 found" in w for w in result.warnings)


def test_adr_id_zero_padded(tmp_repo: Path) -> None:
    body = (
        "# ADR-7: Title\n\n"
        "Status: accepted\nDate: 2026-05-20\n\n"
        "## Decision\n\nDecided.\n"
    )
    p = _adr_file(tmp_repo, "ADR-7-x.md", body)
    result = adr.parse(p, tmp_repo)
    node = next(n for n in result.nodes if n.node_type == NodeType.ADR)
    assert node.properties["adr_id"] == "ADR-007"


def test_idempotent(tmp_repo: Path) -> None:
    body = (
        "# ADR-001: T\n\nStatus: proposed\nDate: 2026-05-20\n\n"
        "## Decision\n\nx.\n"
    )
    p = _adr_file(tmp_repo, "ADR-001-x.md", body)
    a = adr.parse(p, tmp_repo)
    b = adr.parse(p, tmp_repo)
    assert [n.id for n in a.nodes] == [n.id for n in b.nodes]
    assert [n.content_hash for n in a.nodes] == [n.content_hash for n in b.nodes]
