"""WP2.1 / GAP-054 regression guard — importing the CLI must not pull torch.

GAP-054 claimed `src/cli.py` initialized CUDA at import. It does not: the BGE
embedder is lazy + CPU-default and is only constructed by the Pass 3 `cluster`
command. This test pins that invariant so it cannot regress (e.g. a future
module-level `import torch`).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
def test_importing_cli_does_not_import_torch() -> None:
    if importlib.util.find_spec("kuzu") is None:
        pytest.skip("kuzu not installed in this interpreter (use the project .venv)")
    code = (
        "import sys; import src.cli; "
        "bad=[m for m in ('torch','sentence_transformers') if m in sys.modules]; "
        "print(','.join(bad)); sys.exit(1 if bad else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"importing src.cli pulled heavy modules: "
        f"stdout={result.stdout!r} stderr={result.stderr[-500:]!r}"
    )
