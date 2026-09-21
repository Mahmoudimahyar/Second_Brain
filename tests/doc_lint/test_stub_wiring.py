"""WP1 doc-lint — check C: ConflictResolver stub-wiring guard.

The GAP-052 pattern: ``ConflictResolver()`` built with no judge and no
web-verifier on the real path. Per the Wiring Gate that is *not done* — a gap,
not a completion — so the lint fails on any such construction in non-test
``src/`` unless it is explicitly allowlisted (and the allowlist must drain to
empty by the end of WP3).
"""

from __future__ import annotations

from pathlib import Path

from tools.doc_lint.check_status_truth import (
    check_stub_wiring,
    find_constructor_calls,
    find_wiring_sites,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


EMPTY: frozenset[str] = frozenset()


def test_bare_construction_flagged(tmp_path: Path) -> None:
    src = tmp_path / "src"
    _write(
        src / "cli.py",
        "from x import ConflictResolver\n\n"
        "def run() -> None:\n    resolver = ConflictResolver()\n",
    )
    violations = check_stub_wiring(tmp_path, allowlist=EMPTY)
    assert len(violations) == 1
    assert violations[0].kind == "stub_wiring"
    assert "src/cli.py" in violations[0].location
    assert "run" in violations[0].location


def test_wired_construction_passes(tmp_path: Path) -> None:
    src = tmp_path / "src"
    _write(
        src / "flow.py",
        "def build():\n"
        "    return ConflictResolver(judge=j, web_verifier=w)\n",
    )
    assert check_stub_wiring(tmp_path, allowlist=EMPTY) == []


def test_multiline_wired_construction_passes(tmp_path: Path) -> None:
    src = tmp_path / "src"
    _write(
        src / "flow.py",
        "def build():\n"
        "    return ConflictResolver(\n"
        "        judge=make_judge(),\n"
        "        web_verifier=make_verifier(),\n"
        "    )\n",
    )
    assert check_stub_wiring(tmp_path, allowlist=EMPTY) == []


def test_partial_wiring_judge_only_passes(tmp_path: Path) -> None:
    # judge present but no web_verifier: still counts as "wired" for this guard
    # (it is no longer the bare-stub case the Wiring Gate targets).
    src = tmp_path / "src"
    _write(src / "flow.py", "def b():\n    return ConflictResolver(judge=j)\n")
    assert check_stub_wiring(tmp_path, allowlist=EMPTY) == []


def test_allowlisted_bare_construction_passes(tmp_path: Path) -> None:
    src = tmp_path / "src"
    _write(
        src / "cli.py",
        "def reconcile_demo():\n    resolver = ConflictResolver()\n",
    )
    allow = frozenset({"src/cli.py:reconcile_demo"})
    assert check_stub_wiring(tmp_path, allowlist=allow) == []
    # …but the same bare construction in a different function is still flagged.
    _write(
        src / "cli.py",
        "def reconcile_demo():\n    resolver = ConflictResolver()\n\n"
        "def real_ingest():\n    r = ConflictResolver()\n",
    )
    v = check_stub_wiring(tmp_path, allowlist=allow)
    assert len(v) == 1
    assert "real_ingest" in v[0].location


def test_tests_dir_ignored(tmp_path: Path) -> None:
    src = tmp_path / "src"
    _write(src / "conflict" / "tests" / "test_x.py", "ConflictResolver()\n")
    assert check_stub_wiring(tmp_path, allowlist=EMPTY) == []


def test_find_constructor_calls_balances_parens() -> None:
    text = "x = ConflictResolver(judge=Panel(a, b), web_verifier=None)\n"
    calls = find_constructor_calls(text, "ConflictResolver")
    assert len(calls) == 1
    lineno, args = calls[0]
    assert lineno == 1
    assert "judge=Panel(a, b)" in args
    assert "web_verifier=None" in args


def test_find_constructor_calls_skips_identifier_suffix() -> None:
    # `MyConflictResolver(` must NOT match `ConflictResolver(`.
    text = "x = MyConflictResolver()\n"
    assert find_constructor_calls(text, "ConflictResolver") == []


def test_docstring_mention_not_flagged(tmp_path: Path) -> None:
    # A `ConflictResolver()` inside a docstring/comment must NOT be treated as a
    # construction (AST-based detection ignores strings) — only the real call counts.
    src = tmp_path / "src"
    _write(
        src / "factory.py",
        '"""Builds it (historically bare `ConflictResolver()`)."""\n\n'
        "def build():\n    return ConflictResolver(judge=j, web_verifier=w)\n",
    )
    assert check_stub_wiring(tmp_path, allowlist=EMPTY) == []


def test_wiring_site_classification(tmp_path: Path) -> None:
    src = tmp_path / "src"
    _write(src / "a.py", "def f():\n    return ConflictResolver(judge=j, web_verifier=w)\n")
    _write(src / "b.py", "def g():\n    return ConflictResolver()\n")
    sites = find_wiring_sites(tmp_path, allowlist=frozenset({"src/b.py:g"}))
    by_key = {s.key: s for s in sites}
    assert by_key["src/a.py:f"].wired is True
    assert by_key["src/b.py:g"].wired is False
    assert by_key["src/b.py:g"].allowlisted is True
