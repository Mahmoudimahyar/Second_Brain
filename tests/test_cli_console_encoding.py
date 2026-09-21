"""Regression guard — CLI output must not crash on a non-UTF-8 console.

Help text contains characters such as "→" and "ù" (Kùzu). When stdout is piped or
belongs to a legacy Windows console, Python encodes with cp1252 and
`secbrain ingest l5-reddit --help` died with a `UnicodeEncodeError` traceback —
a bad first impression for anyone trying the tool. The CLI now forces UTF-8 with
replacement on its own streams.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "args",
    [
        ["--help"],
        ["ingest", "--help"],
        ["ingest", "l5-reddit", "--help"],
        ["ingest", "l1-adea", "--help"],
        ["crawl", "--help"],
    ],
)
def test_help_survives_legacy_console_encoding(args: list[str]) -> None:
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    proc = subprocess.run(
        [sys.executable, "-m", "src.cli", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, timeout=180, check=False,
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined.decode("utf-8", "replace")[-600:]
    assert b"UnicodeEncodeError" not in combined
    assert b"Traceback" not in combined
