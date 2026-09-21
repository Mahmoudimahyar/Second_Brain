"""Smoke tests for `flows/` Prefect scaffolds.

Prefect is an OPTIONAL dependency (`pyproject.toml` `[project.optional-dependencies.orchestration]`).
These tests validate file syntactic correctness via `ast.parse` so they pass
without Prefect installed, then check that all expected entry-points exist by
inspecting the AST.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_FLOWS_DIR = Path(__file__).parent.parent / "flows"

EXPECTED_FLOWS = {
    "pass1_structural.py": "pass1_structural_incremental",
    "pass2_labels.py": "pass2_labels_incremental",
    "pass3_clustering.py": "pass3_clustering_weekly",
    "pass4_llm.py": "pass4_llm_daily",
    "pass5_indexing.py": "pass5_indexing_refresh",
    "full_sweep.py": "full_sweep",
}


@pytest.mark.parametrize("filename,flow_name", list(EXPECTED_FLOWS.items()))
def test_flow_file_is_valid_python_and_defines_flow(
    filename: str, flow_name: str,
) -> None:
    path = _FLOWS_DIR / filename
    assert path.is_file(), f"flow file missing: {filename}"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=filename)
    funcnames = {
        node.name for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    assert flow_name in funcnames, (
        f"{filename} must define `{flow_name}` (expected Prefect @flow entry-point)"
    )


def test_init_lists_run_instructions() -> None:
    init_path = _FLOWS_DIR / "__init__.py"
    assert init_path.is_file()
    text = init_path.read_text(encoding="utf-8")
    assert "prefect server start" in text
    assert "ADR-010" in text


def test_orchestration_optional_dep_declared() -> None:
    """ADR-010: Prefect listed as an optional install group, not a hard runtime dep."""

    pyproject = (Path(__file__).parent.parent / "pyproject.toml").read_text(
        encoding="utf-8",
    )
    assert "orchestration = [" in pyproject
    assert "prefect>=3" in pyproject
