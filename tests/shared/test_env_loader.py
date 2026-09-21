"""Tests for `src.shared.env_loader.load_dotenv`."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.shared.env_loader import load_dotenv


def test_loads_simple_key_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FOO_TEST", raising=False)
    env = tmp_path / ".env"
    env.write_text("FOO_TEST=bar\n", encoding="utf-8")

    count = load_dotenv(env)

    assert count == 1
    assert os.environ["FOO_TEST"] == "bar"


def test_skips_comments_and_blanks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("X1", raising=False)
    monkeypatch.delenv("X2", raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "# header\n\nX1=one\n# comment\nX2=two\n",
        encoding="utf-8",
    )

    count = load_dotenv(env)

    assert count == 2
    assert os.environ["X1"] == "one"
    assert os.environ["X2"] == "two"


def test_inline_comments_stripped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KEY_WITH_COMMENT", raising=False)
    env = tmp_path / ".env"
    env.write_text("KEY_WITH_COMMENT=value  # trailing\n", encoding="utf-8")

    load_dotenv(env)
    assert os.environ["KEY_WITH_COMMENT"] == "value"


def test_existing_nonempty_env_var_is_not_overridden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXISTING", "shell_value")
    env = tmp_path / ".env"
    env.write_text("EXISTING=file_value\n", encoding="utf-8")

    load_dotenv(env)
    assert os.environ["EXISTING"] == "shell_value"


def test_empty_shell_var_is_overridden_by_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows shadow-var workaround: empty shell vars treated as missing."""

    monkeypatch.setenv("EMPTY_SHADOW", "")
    env = tmp_path / ".env"
    env.write_text("EMPTY_SHADOW=file_value\n", encoding="utf-8")

    load_dotenv(env)
    assert os.environ["EMPTY_SHADOW"] == "file_value"


def test_missing_file_returns_zero(tmp_path: Path) -> None:
    count = load_dotenv(tmp_path / "missing.env")
    assert count == 0


def test_handles_keys_with_dashes_and_underscores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MY_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("MY_API_KEY=sk-xxx-yyy\n", encoding="utf-8")

    load_dotenv(env)
    assert os.environ["MY_API_KEY"] == "sk-xxx-yyy"


def test_no_equals_lines_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VALID", raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "not a key value line\nVALID=ok\nanother bad line\n",
        encoding="utf-8",
    )

    count = load_dotenv(env)
    assert count == 1
    assert os.environ["VALID"] == "ok"
