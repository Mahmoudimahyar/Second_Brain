"""`.env.example` and docs/guide/configuration.md must describe reality, in both directions.

* every environment variable the code reads is documented, and
* every variable `.env.example` offers is actually read by some code.

The second direction is the one that had drifted: the file once listed ~30 planned settings
that nothing consumed.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO_ROOT / ".env.example"
CONFIG_DOC = REPO_ROOT / "docs" / "guide" / "configuration.md"

_READ = re.compile(
    r"""(?:environ(?:\.get)?\s*[\(\[]\s*|getenv\s*\(\s*|envvar\s*=\s*|api_key_env(?::\s*str)?\s*=\s*"""
    r"""|_ENV\w*\s*(?::\s*str\s*)?=\s*)["']([A-Z][A-Z0-9_]{2,})["']""",
)
_WILDCARD = re.compile(r"`([A-Z][A-Z0-9_]*_)\*`")
# Standard variables owned by the OS / toolchain rather than by SecBrain.
_NOT_OURS = {"PATH", "HOME", "USERPROFILE", "PYTHONIOENCODING"}


def _code_files() -> list[Path]:
    """Tracked .py files under src/ flows/ tools/ (falls back to a walk outside a git checkout)."""

    proc = subprocess.run(
        ["git", "ls-files", "src", "flows", "tools"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return [REPO_ROOT / f for f in proc.stdout.splitlines() if f.endswith(".py")]
    return [
        path for top in ("src", "flows", "tools") for path in (REPO_ROOT / top).rglob("*.py")
        if "__pycache__" not in path.parts
    ]


def _vars_read_by_code() -> set[str]:
    found: set[str] = set()
    for path in _code_files():
        found.update(_READ.findall(path.read_text(encoding="utf-8", errors="replace")))
    return found - _NOT_OURS


def test_every_variable_the_code_reads_is_documented() -> None:
    doc = CONFIG_DOC.read_text(encoding="utf-8")
    prefixes = tuple(_WILDCARD.findall(doc))
    missing = sorted(
        v for v in _vars_read_by_code()
        if f"`{v}`" not in doc and not v.startswith(prefixes)
    )
    assert not missing, f"undocumented in docs/guide/configuration.md: {missing}"


def test_env_example_offers_nothing_the_code_ignores() -> None:
    offered = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]{2,})=", ENV_EXAMPLE.read_text(encoding="utf-8"), re.M))
    code = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in _code_files())
    unused = sorted(v for v in offered if not re.search(rf"\b{re.escape(v)}\b", code))
    assert not unused, f".env.example offers variables no code reads: {unused}"
