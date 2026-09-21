"""Tests for `tools/graphrag/parsers/config.py`."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.graphrag.parsers import config
from tools.graphrag.parsers.base import accepts_path
from tools.graphrag.types import NodeType

pytestmark = pytest.mark.unit


class _StubParser:
    ACCEPTS = config.ACCEPTS

    def parse(self, file_path, repo_root):  # pragma: no cover
        return None


def test_accepts_env_and_pyproject() -> None:
    p = _StubParser()
    assert accepts_path(p, ".env.example")
    assert accepts_path(p, "pyproject.toml")


def test_rejects_unrelated() -> None:
    p = _StubParser()
    assert not accepts_path(p, ".env")
    assert not accepts_path(p, "package.json")


def test_env_example_keys_extracted(tmp_repo: Path) -> None:
    body = (
        "# LLM vendors\n"
        "# Anthropic API key (required)\n"
        "ANTHROPIC_API_KEY=\n\n"
        "# OpenAI key — optional unless using GPT for judging\n"
        "OPENAI_API_KEY=\n\n"
        "# Behavior flags\n"
        "PROMPT_CACHE_TTL_SECONDS=3600\n"
    )
    path = tmp_repo / ".env.example"
    path.write_text(body, encoding="utf-8")
    result = config.parse(path, tmp_repo)

    keys = {n.properties["key"]: n for n in result.nodes if n.node_type == NodeType.CONFIG_KEY}
    assert set(keys) == {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "PROMPT_CACHE_TTL_SECONDS"}
    assert keys["ANTHROPIC_API_KEY"].properties["required"] is True
    assert keys["OPENAI_API_KEY"].properties["required"] is False
    assert keys["PROMPT_CACHE_TTL_SECONDS"].properties["required"] is False
    assert "Anthropic" in keys["ANTHROPIC_API_KEY"].properties["description"]


def test_pyproject_project_keys_extracted(tmp_repo: Path) -> None:
    body = (
        '[project]\n'
        'name = "secbrain"\n'
        'version = "0.1.0"\n'
        'requires-python = ">=3.12"\n\n'
        '[project.scripts]\n'
        'graphrag-index = "tools.graphrag.cli:index_command"\n'
    )
    path = tmp_repo / "pyproject.toml"
    path.write_text(body, encoding="utf-8")
    result = config.parse(path, tmp_repo)

    keys = {n.properties["key"] for n in result.nodes if n.node_type == NodeType.CONFIG_KEY}
    assert "name" in keys
    assert "version" in keys
    assert "requires-python" in keys
    assert "graphrag-index" in keys


def test_pyproject_required_flag(tmp_repo: Path) -> None:
    body = (
        '[project]\n'
        'name = "x"\n'
        'version = "0.1"\n'
        'requires-python = ">=3.12"\n'
        'description = "blah"\n'
    )
    path = tmp_repo / "pyproject.toml"
    path.write_text(body, encoding="utf-8")
    result = config.parse(path, tmp_repo)

    required = {
        n.properties["key"]
        for n in result.nodes
        if n.node_type == NodeType.CONFIG_KEY and n.properties["required"]
    }
    assert required == {"name", "version", "requires-python"}


def test_idempotent(tmp_repo: Path) -> None:
    path = tmp_repo / ".env.example"
    path.write_text("KEY=value\n", encoding="utf-8")
    a = config.parse(path, tmp_repo)
    b = config.parse(path, tmp_repo)
    assert [n.id for n in a.nodes] == [n.id for n in b.nodes]
