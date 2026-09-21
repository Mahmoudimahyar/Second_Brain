"""Shared pytest fixtures for the graphrag test suite."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Iterator[Path]:
    """A temporary repo root with a `.gitignore` to satisfy parsers that key off the root."""

    (tmp_path / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    yield tmp_path
