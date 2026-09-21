"""Tests for `tools/graphrag/parsers/context_pack.py`."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.graphrag.parsers import context_pack
from tools.graphrag.parsers.base import accepts_path
from tools.graphrag.types import NodeType

pytestmark = pytest.mark.unit


class _StubParser:
    ACCEPTS = context_pack.ACCEPTS

    def parse(self, file_path, repo_root):  # pragma: no cover
        return None


def test_accepts_pack_readme() -> None:
    p = _StubParser()
    assert accepts_path(p, "docs/14-context-packs/v1-slice-implementation/README.md")


def test_rejects_root_readme_and_other_files() -> None:
    p = _StubParser()
    assert not accepts_path(p, "docs/14-context-packs/README.md")
    assert not accepts_path(p, "docs/14-context-packs/v1-slice/required-reading.md")


def test_emits_context_pack(tmp_repo: Path) -> None:
    pack_dir = tmp_repo / "docs" / "14-context-packs" / "v1-slice"
    pack_dir.mkdir(parents=True)
    (pack_dir / "README.md").write_text(
        "# v1-slice implementation pack\n\n"
        "Use when starting Phase 1+ of the V1 slice.\n\n"
        "Second paragraph (not included in purpose).\n",
        encoding="utf-8",
    )

    result = context_pack.parse(pack_dir / "README.md", tmp_repo)

    nodes = [n for n in result.nodes if n.node_type == NodeType.CONTEXT_PACK]
    assert len(nodes) == 1
    node = nodes[0]
    assert node.id == "pack:v1-slice"
    assert node.properties["pack_name"] == "v1-slice"
    assert "Use when" in node.properties["purpose"]
    assert "Second paragraph" not in node.properties["purpose"]


def test_root_readme_returns_no_pack(tmp_repo: Path) -> None:
    pack_dir = tmp_repo / "docs" / "14-context-packs"
    pack_dir.mkdir(parents=True)
    (pack_dir / "README.md").write_text("# Context Packs\n\nThe directory.\n", encoding="utf-8")

    result = context_pack.parse(pack_dir / "README.md", tmp_repo)

    assert result.nodes == []


def test_idempotent(tmp_repo: Path) -> None:
    pack_dir = tmp_repo / "docs" / "14-context-packs" / "x"
    pack_dir.mkdir(parents=True)
    (pack_dir / "README.md").write_text("# X\n\npurpose.\n", encoding="utf-8")
    a = context_pack.parse(pack_dir / "README.md", tmp_repo)
    b = context_pack.parse(pack_dir / "README.md", tmp_repo)
    assert [n.id for n in a.nodes] == [n.id for n in b.nodes]
