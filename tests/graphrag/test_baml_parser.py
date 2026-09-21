"""Tests for `tools/graphrag/parsers/baml.py` (V1 stub).

Stub behavior: ACCEPTS `src/prompts/*.baml` but emits no nodes until BAML files land in V1.x.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.graphrag.parsers import baml
from tools.graphrag.parsers.base import accepts_path
from tools.graphrag.types import ParseResult

pytestmark = pytest.mark.unit


class _StubParser:
    ACCEPTS = baml.ACCEPTS

    def parse(self, file_path, repo_root):  # pragma: no cover
        return None


def test_accepts_baml_under_prompts() -> None:
    p = _StubParser()
    assert accepts_path(p, "src/prompts/stage3_sentiment.baml")


def test_rejects_baml_elsewhere() -> None:
    p = _StubParser()
    assert not accepts_path(p, "tools/graphrag/something.baml")


def test_stub_does_not_crash_on_synthetic_baml(tmp_repo: Path) -> None:
    prompts_dir = tmp_repo / "src" / "prompts"
    prompts_dir.mkdir(parents=True)
    p = prompts_dir / "stage3_sentiment.baml"
    p.write_text("function ExtractSentiment(text: string) -> string\n", encoding="utf-8")

    result = baml.parse(p, tmp_repo)

    assert isinstance(result, ParseResult)
    assert result.nodes == []
    assert result.edges == []


def test_stub_handles_missing_file(tmp_repo: Path) -> None:
    p = tmp_repo / "src" / "prompts" / "missing.baml"
    result = baml.parse(p, tmp_repo)
    assert result.nodes == []
