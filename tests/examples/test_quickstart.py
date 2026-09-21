"""The quickstart in `examples/quickstart/` is documentation that must stay true.

Runs the same steps the README walks through — generate fictional data, ingest an L1
reference sheet and an L5 forum through the real CLI, resolve an alias, query, and walk the
conflict cascade — and asserts the outputs the README promises.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from typer.testing import CliRunner

from src.cli import app

QUICKSTART = Path(__file__).resolve().parents[2] / "examples" / "quickstart"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"quickstart_{name}", QUICKSTART / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def demo(tmp_path: Path) -> tuple[CliRunner, Path, Path]:
    inputs = tmp_path / "in"
    assert _load("make_demo_data").main([str(inputs)]) == 0
    return CliRunner(), inputs, tmp_path / "data"


def _run(runner: CliRunner, data_dir: Path, *args: str) -> str:
    result = runner.invoke(
        app, ["--data-dir", str(data_dir), "--env-file", str(data_dir / "none.env"), *args],
    )
    assert result.exit_code == 0, result.output
    return result.output


def test_quickstart_walkthrough(demo: tuple[CliRunner, Path, Path]) -> None:
    runner, inputs, data_dir = demo

    out = _run(runner, data_dir, "ingest", "l1-adea", str(inputs / "reference_2024-25.xlsx"))
    assert "schools=5" in out and "metrics=10" in out

    out = _run(runner, data_dir, "ingest", "l5-reddit",
               str(inputs / "demo_forum.jsonl"), str(inputs / "demo_forum_comments.jsonl"))
    assert "r/demo_forum" in out
    assert "posts=10" in out and "comments=12" in out and "users=7" in out
    assert "topics=4" in out

    out = _run(runner, data_dir, "stats")
    assert "School" in out and "Topic" in out and "Total nodes: 50" in out

    out = _run(runner, data_dir, "canonical", "Lakemont")
    assert "school:lakemont_college_of_dental_medicine" in out
    assert "LCDM" in out                      # acronym alias derived, never typed by anyone
    assert "No L1 match" in _run(runner, data_dir, "canonical", "Hogwarts Dental")

    out = _run(runner, data_dir, "query", "Marlowe", "--no-hybrid", "--limit", "5")
    first_l1 = out.index("school:marlowe")
    first_l5 = out.index("reddit_post:")
    assert first_l1 < first_l5                # official record first, community after


def test_conflict_cascade_outcomes(capsys: pytest.CaptureFixture[str]) -> None:
    assert _load("conflict_cascade").main() == 0
    out = capsys.readouterr().out
    statuses = [line.split()[1] for line in out.splitlines() if line.strip().startswith("→")]
    assert statuses == ["l1_clash_invalidated", "temporal_split", "trust_weighted", "hitl_pending"]
