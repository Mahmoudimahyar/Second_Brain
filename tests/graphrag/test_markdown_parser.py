"""Tests for `tools/graphrag/parsers/markdown.py`.

Failing-first per AGENTS.md TDD discipline. Covers acceptance criteria for the markdown parser
listed in `tools/graphrag/verification-harness.md`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.graphrag.parsers import markdown
from tools.graphrag.parsers.base import accepts_path
from tools.graphrag.types import EdgeType, NodeType

pytestmark = pytest.mark.unit


# ---------- ACCEPTS pattern ----------


class _StubParser:
    ACCEPTS = markdown.ACCEPTS

    def parse(self, file_path, repo_root):  # pragma: no cover - protocol stub
        return None


def test_accepts_md_files() -> None:
    p = _StubParser()
    assert accepts_path(p, "docs/01-core/product-vision.md")
    assert accepts_path(p, "README.md")
    assert accepts_path(p, "tools/graphrag/architecture.markdown")


def test_rejects_non_markdown_files() -> None:
    p = _StubParser()
    assert not accepts_path(p, "src/extraction/cascade.py")
    assert not accepts_path(p, "pyproject.toml")
    assert not accepts_path(p, "data/dumps/payload.zst")


# ---------- DocPage emission ----------


def test_emits_exactly_one_docpage(tmp_repo: Path) -> None:
    md_path = tmp_repo / "notes.md"
    md_path.write_text("# Title\n\nBody text.\n", encoding="utf-8")

    result = markdown.parse(md_path, tmp_repo)

    page_nodes = [n for n in result.nodes if n.node_type == NodeType.DOC_PAGE]
    assert len(page_nodes) == 1
    page = page_nodes[0]
    assert page.id == "doc:notes.md"
    assert page.source_path == "notes.md"
    assert page.properties["title"] == "Title"
    assert page.properties["section_count"] == 1
    assert page.content_hash is not None


def test_docpage_title_falls_back_to_filename_when_no_h1(tmp_repo: Path) -> None:
    md_path = tmp_repo / "no-h1.md"
    md_path.write_text("Just body, no heading.\n", encoding="utf-8")

    result = markdown.parse(md_path, tmp_repo)

    page = next(n for n in result.nodes if n.node_type == NodeType.DOC_PAGE)
    assert page.properties["title"] == "no-h1"
    assert page.properties["section_count"] == 0


# ---------- DocSection emission ----------


def test_emits_one_section_per_heading(tmp_repo: Path) -> None:
    md_path = tmp_repo / "multi.md"
    md_path.write_text(
        "# H1\n\nIntro.\n\n## H2-a\n\nBody A.\n\n## H2-b\n\nBody B.\n\n### H3\n\nDeep.\n",
        encoding="utf-8",
    )

    result = markdown.parse(md_path, tmp_repo)

    section_nodes = [n for n in result.nodes if n.node_type == NodeType.DOC_SECTION]
    headings = [n.properties["heading"] for n in section_nodes]
    assert headings == ["H1", "H2-a", "H2-b", "H3"]
    levels = [n.properties["level"] for n in section_nodes]
    assert levels == [1, 2, 2, 3]


def test_section_body_extends_to_next_equal_or_shallower_heading(tmp_repo: Path) -> None:
    md_path = tmp_repo / "nested.md"
    md_path.write_text(
        "## Parent\n\nParent body.\n\n### Child\n\nChild body.\n\n## Sibling\n\nSibling body.\n",
        encoding="utf-8",
    )

    result = markdown.parse(md_path, tmp_repo)

    parent = next(n for n in result.nodes if n.properties.get("heading") == "Parent")
    child = next(n for n in result.nodes if n.properties.get("heading") == "Child")
    sibling = next(n for n in result.nodes if n.properties.get("heading") == "Sibling")

    assert "Parent body." in parent.properties["text"]
    # Parent contains its descendants' text too — that's by design (text is "everything until
    # next equal-or-shallower heading"). Child + Sibling are separately emitted nodes.
    assert "Child body." in parent.properties["text"]
    assert "Sibling body." not in parent.properties["text"]
    assert child.properties["text"].strip() == "Child body."
    assert sibling.properties["text"].strip() == "Sibling body."


def test_anchors_are_url_safe_slugs(tmp_repo: Path) -> None:
    md_path = tmp_repo / "slugs.md"
    md_path.write_text(
        "# Hello, World!\n\nFoo.\n\n## Section: Two\n\nBar.\n",
        encoding="utf-8",
    )

    result = markdown.parse(md_path, tmp_repo)

    anchors = [
        n.properties["anchor"]
        for n in result.nodes
        if n.node_type == NodeType.DOC_SECTION
    ]
    assert anchors == ["hello-world", "section-two"]


def test_duplicate_anchors_disambiguated_and_warned(tmp_repo: Path) -> None:
    md_path = tmp_repo / "dupes.md"
    md_path.write_text(
        "# Setup\n\nA.\n\n## Setup\n\nB.\n\n## Setup\n\nC.\n",
        encoding="utf-8",
    )

    result = markdown.parse(md_path, tmp_repo)

    anchors = [
        n.properties["anchor"]
        for n in result.nodes
        if n.node_type == NodeType.DOC_SECTION
    ]
    assert anchors[0] == "setup"
    assert anchors[1] == "setup-1"
    assert anchors[2] == "setup-2"
    assert any("duplicate heading anchor" in w for w in result.warnings)


# ---------- Edges ----------


def test_docpage_has_section_edges(tmp_repo: Path) -> None:
    md_path = tmp_repo / "edges.md"
    md_path.write_text("# A\n\nbody\n\n## B\n\nbody\n", encoding="utf-8")

    result = markdown.parse(md_path, tmp_repo)

    edges = [e for e in result.edges if e.edge_type == EdgeType.DOC_PAGE_HAS_SECTION]
    assert len(edges) == 2
    page_id = "doc:edges.md"
    for e in edges:
        assert e.from_node_id == page_id
        assert e.to_node_id.startswith(page_id + "#")


# ---------- Frontmatter ----------


def test_yaml_frontmatter_extracted(tmp_repo: Path) -> None:
    md_path = tmp_repo / "fm.md"
    md_path.write_text(
        "---\nstatus: draft\ntags:\n  - test\n  - graphrag\n---\n\n# Body\n\nText.\n",
        encoding="utf-8",
    )

    result = markdown.parse(md_path, tmp_repo)

    page = next(n for n in result.nodes if n.node_type == NodeType.DOC_PAGE)
    assert page.properties["frontmatter"]["status"] == "draft"
    assert page.properties["frontmatter"]["tags"] == ["test", "graphrag"]


def test_malformed_frontmatter_does_not_crash(tmp_repo: Path) -> None:
    md_path = tmp_repo / "bad-fm.md"
    md_path.write_text(
        "---\nstatus: draft\n  malformed-indent:\n---\n\n# Body\n",
        encoding="utf-8",
    )

    result = markdown.parse(md_path, tmp_repo)

    page = next(n for n in result.nodes if n.node_type == NodeType.DOC_PAGE)
    # Malformed YAML → empty dict, body still parsed normally.
    assert isinstance(page.properties["frontmatter"], dict)
    assert page.properties["title"] in ("Body", "bad-fm")


# ---------- Idempotency ----------


def test_parse_is_deterministic(tmp_repo: Path) -> None:
    md_path = tmp_repo / "idem.md"
    md_path.write_text("# T\n\nbody\n\n## S\n\nmore\n", encoding="utf-8")

    a = markdown.parse(md_path, tmp_repo)
    b = markdown.parse(md_path, tmp_repo)
    assert [(n.id, n.content_hash) for n in a.nodes] == [
        (n.id, n.content_hash) for n in b.nodes
    ]
    assert [(e.id, e.edge_type) for e in a.edges] == [
        (e.id, e.edge_type) for e in b.edges
    ]


def test_content_hash_changes_on_body_change(tmp_repo: Path) -> None:
    md_path = tmp_repo / "h.md"
    md_path.write_text("# T\n\nv1\n", encoding="utf-8")
    a = markdown.parse(md_path, tmp_repo)
    md_path.write_text("# T\n\nv2\n", encoding="utf-8")
    b = markdown.parse(md_path, tmp_repo)

    page_a = next(n for n in a.nodes if n.node_type == NodeType.DOC_PAGE)
    page_b = next(n for n in b.nodes if n.node_type == NodeType.DOC_PAGE)
    assert page_a.content_hash != page_b.content_hash
