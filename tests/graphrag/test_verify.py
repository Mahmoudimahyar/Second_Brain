"""Tests for `tools/graphrag/verify.py` — gate #6 harness."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.graphrag.index import index_full
from tools.graphrag.store.sqlite_client import SQLiteGraphClient
from tools.graphrag.verify import render_report, run_verification

pytestmark = pytest.mark.integration


def _build_fixture(root: Path) -> None:
    (root / ".gitignore").write_text("", encoding="utf-8")

    (root / "AGENTS.md").write_text(
        "# AGENTS\n\nUse GraphRAG/MCP retrieval before broad reads.\n",
        encoding="utf-8",
    )

    docs = root / "docs" / "01-core"
    docs.mkdir(parents=True)
    (docs / "vision.md").write_text(
        "# Vision\n\n## Goals\n\nDoc references `src/gateway.py`.\n",
        encoding="utf-8",
    )

    slice_dir = root / "docs" / "05-features" / "01-demo"
    slice_dir.mkdir(parents=True)
    (slice_dir / "README.md").write_text(
        "# Feature: Demo\n\n**Status:** Proposed.\n",
        encoding="utf-8",
    )
    (slice_dir / "requirements.md").write_text(
        "- **FR-1.1** First.\n- **NFR-1 Latency**: fast.\n",
        encoding="utf-8",
    )
    (slice_dir / "test-plan.md").write_text(
        "### AC-1 — Demo (FR-1.1)\n\nbody\n",
        encoding="utf-8",
    )

    adr_dir = root / "docs" / "11-decisions"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-001-x.md").write_text(
        "# ADR-001: First\n\nStatus: accepted\nDate: 2026-05-21\n\n"
        "## Decision\n\nFirst paragraph.\n",
        encoding="utf-8",
    )

    src = root / "src"
    src.mkdir()
    (src / "gateway.py").write_text("def call() -> int:\n    return 1\n", encoding="utf-8")

    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_demo.py").write_text(
        "def test_x() -> None:\n"
        '    """Covers FR-1.1 and AC-1."""\n'
        "    assert True\n",
        encoding="utf-8",
    )


@pytest.fixture
def verified(tmp_path: Path):
    repo = tmp_path / "fixture"
    repo.mkdir()
    _build_fixture(repo)
    store = SQLiteGraphClient(tmp_path / "graph.db")
    index_full(repo, store)
    report = run_verification(repo, store)
    yield report, store, repo
    store.close()


def test_overall_pass_on_fixture(verified) -> None:
    report, _store, _repo = verified
    assert report.overall == "PASS", "\n".join(
        f"{c.name}: {c.status} — {c.notes}" for c in report.checks if c.status == "fail"
    )


def test_no_fail_checks(verified) -> None:
    report, _store, _repo = verified
    fails = [c for c in report.checks if c.status == "fail"]
    assert fails == [], [(c.name, c.notes) for c in fails]


def test_all_required_checks_present(verified) -> None:
    report, _store, _repo = verified
    names = {c.name for c in report.checks}
    expected = {
        "docs parsed into DocPage/DocSection nodes",
        "code parsed into CodeFile/Function/Class nodes",
        "tests parsed into TestFile/TestCase nodes",
        "feature packets indexed",
        "frontmatter metadata indexed",
        "Feature → Requirement edges",
        "Requirement → AcceptanceCriterion edges",
        "Feature → Docs edges",
        "DocSection → CodeFile/Symbol edges",
        "feature context retrieval works",
        "symbol lookup works",
        "related tests retrieval works",
        "docs-for-code retrieval works",
        "code-for-doc retrieval works",
        "stale docs detection exists or is planned",
        "AGENTS.md tells agents to use GraphRAG/MCP",
        "fallback behavior exists if GraphRAG unavailable",
        "retrieval logs are stored",
        "token usage is measured",
    }
    missing = expected - names
    assert not missing, f"checks missing from harness: {missing}"


def test_render_report_produces_markdown(verified) -> None:
    report, _store, _repo = verified
    md = render_report(report)
    assert "# GraphRAG Verification" in md
    assert "**OVERALL: PASS**" in md
    assert "| Check | Status |" in md


def test_agents_md_check_fails_when_missing(tmp_path: Path) -> None:
    repo = tmp_path / "fixture"
    repo.mkdir()
    _build_fixture(repo)
    (repo / "AGENTS.md").unlink()
    store = SQLiteGraphClient(tmp_path / "graph.db")
    index_full(repo, store)
    report = run_verification(repo, store)
    agents_check = next(
        c for c in report.checks if c.name == "AGENTS.md tells agents to use GraphRAG/MCP"
    )
    assert agents_check.status == "fail"
    store.close()


def test_strict_mode_can_flag_missing_code(tmp_path: Path) -> None:
    """In strict mode + no src/, the code-parsed check fails."""

    repo = tmp_path / "fixture"
    repo.mkdir()
    _build_fixture(repo)
    # Remove the only code file
    (repo / "src" / "gateway.py").unlink()
    store = SQLiteGraphClient(tmp_path / "graph.db")
    index_full(repo, store)
    report = run_verification(repo, store, strict=True)
    code_check = next(c for c in report.checks if c.name == "code parsed into CodeFile/Function/Class nodes")
    assert code_check.status == "fail"
    store.close()
