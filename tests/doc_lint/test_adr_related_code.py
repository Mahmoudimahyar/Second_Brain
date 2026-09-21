"""WP1 doc-lint — check A: ADR 'Related code' files must exist.

Covers the GAP-050 pattern: an ADR marked ``Status: accepted`` that lists
``Related code`` files which do not exist on disk. The check must:

- enforce existence for *uncaveated* ``## Related code`` sections of accepted ADRs;
- IGNORE sections explicitly marked deferred (``(to be created in V1.7 …)``,
  ``(spike …)``) — those decisions whose code lands later in V1.7;
- IGNORE ``proposed`` ADRs entirely;
- handle both ADR header formats (markdown ``Status:`` line and YAML frontmatter).
"""

from __future__ import annotations

from pathlib import Path

from tools.doc_lint.check_status_truth import (
    check_adr_related_code,
    parse_adr,
)

# --------------------------------------------------------------------------
# Fixtures: synthetic ADR + repo builders
# --------------------------------------------------------------------------

FORMAT_A_ACCEPTED = """\
# ADR-099: Synthetic Accepted Decision

Status: **accepted**
Date: 2026-05-29

## Decision

Do the thing.

## Related code

- `src/synthetic/widget.py` — the widget
- `tests/synthetic/test_widget.py` — its tests
"""

FORMAT_A_DEFERRED = """\
# ADR-098: Synthetic Accepted-But-Deferred Decision

Status: **accepted**

## Related code (to be created in V1.7 — GAP-099)

- `src/synthetic/not_yet.py` — built later in V1.7
"""

FORMAT_A_PROPOSED = """\
# ADR-097: Synthetic Proposed Spike

Status: **proposed** (2026-05-29) — decision deferred to a spike.

## Related code (spike only — created when the spike runs)

- `tools/synthetic_bakeoff/` — harness
"""

FORMAT_B_ACCEPTED = """\
---
adr: 096
title: Synthetic frontmatter decision
status: accepted
date: 2026-05-24
---

# ADR-096 — Synthetic frontmatter decision

## Related code

- `src/synthetic/frontmatter.py` — the thing
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _adr_dir(tmp_path: Path) -> Path:
    return tmp_path / "docs" / "11-decisions"


# --------------------------------------------------------------------------
# parse_adr
# --------------------------------------------------------------------------


def test_parse_format_a_status(tmp_path: Path) -> None:
    p = _adr_dir(tmp_path) / "ADR-099-x.md"
    _write(p, FORMAT_A_ACCEPTED)
    info = parse_adr(p)
    assert info.status == "accepted"
    assert info.number == 99
    assert info.related_code is not None
    assert info.related_code.deferred is False
    assert "src/synthetic/widget.py" in info.related_code.files
    assert "tests/synthetic/test_widget.py" in info.related_code.files


def test_parse_format_b_frontmatter_status(tmp_path: Path) -> None:
    p = _adr_dir(tmp_path) / "ADR-096-x.md"
    _write(p, FORMAT_B_ACCEPTED)
    info = parse_adr(p)
    assert info.status == "accepted"
    assert info.number == 96
    assert info.related_code is not None
    assert "src/synthetic/frontmatter.py" in info.related_code.files


def test_parse_deferred_related_code_heading(tmp_path: Path) -> None:
    p = _adr_dir(tmp_path) / "ADR-098-x.md"
    _write(p, FORMAT_A_DEFERRED)
    info = parse_adr(p)
    assert info.status == "accepted"
    assert info.related_code is not None
    assert info.related_code.deferred is True


def test_parse_spike_related_code_heading(tmp_path: Path) -> None:
    p = _adr_dir(tmp_path) / "ADR-097-x.md"
    _write(p, FORMAT_A_PROPOSED)
    info = parse_adr(p)
    assert info.status == "proposed"
    assert info.related_code is not None
    assert info.related_code.deferred is True


def test_related_code_strips_symbol_and_line_suffix(tmp_path: Path) -> None:
    text = (
        "# ADR-095: Wiring suffix\n\nStatus: **accepted**\n\n"
        "## Related code\n\n"
        "- Wiring: `src/retrieval/api.py:query_graph` must call the scorer\n"
        "- `src/graph/kuzu_client.py:128` — the writer\n"
    )
    p = _adr_dir(tmp_path) / "ADR-095-x.md"
    _write(p, text)
    info = parse_adr(p)
    assert info.related_code is not None
    # `:query_graph` (symbol) and `:128` (line) are stripped to bare paths.
    assert "src/retrieval/api.py" in info.related_code.files
    assert "src/graph/kuzu_client.py" in info.related_code.files


def test_parse_ignores_backtick_non_paths(tmp_path: Path) -> None:
    text = (
        "# ADR-094: Non-paths\n\nStatus: **accepted**\n\n"
        "## Related code\n\n"
        "- `ConflictResolver(judge=…)` — construct with the judge\n"
        "- `src/conflict/resolver.py` — the resolver\n"
    )
    p = _adr_dir(tmp_path) / "ADR-094-x.md"
    _write(p, text)
    info = parse_adr(p)
    assert info.related_code is not None
    # A backtick code-token with no path separator is not a file to check.
    assert info.related_code.files == ["src/conflict/resolver.py"]


# --------------------------------------------------------------------------
# check_adr_related_code
# --------------------------------------------------------------------------


def test_flags_missing_file_in_accepted_uncaveated(tmp_path: Path) -> None:
    _write(_adr_dir(tmp_path) / "ADR-099-x.md", FORMAT_A_ACCEPTED)
    # Neither referenced file exists.
    violations = check_adr_related_code(tmp_path)
    locations = {v.location for v in violations}
    assert any("widget.py" in m for m in (v.message for v in violations))
    # Both missing files are reported.
    assert len(violations) == 2
    assert all(v.kind == "adr_related_code" for v in violations)
    assert any("ADR-099" in loc for loc in locations)


def test_passes_when_files_exist(tmp_path: Path) -> None:
    _write(_adr_dir(tmp_path) / "ADR-099-x.md", FORMAT_A_ACCEPTED)
    _write(tmp_path / "src" / "synthetic" / "widget.py", "# widget\n")
    _write(tmp_path / "tests" / "synthetic" / "test_widget.py", "# test\n")
    assert check_adr_related_code(tmp_path) == []


def test_ignores_deferred_section(tmp_path: Path) -> None:
    _write(_adr_dir(tmp_path) / "ADR-098-x.md", FORMAT_A_DEFERRED)
    # `src/synthetic/not_yet.py` is absent, but the section is deferred.
    assert check_adr_related_code(tmp_path) == []


def test_ignores_proposed_adr(tmp_path: Path) -> None:
    _write(_adr_dir(tmp_path) / "ADR-097-x.md", FORMAT_A_PROPOSED)
    assert check_adr_related_code(tmp_path) == []


MIXED_SECTION = """\
# ADR-093: Mixed built + not-yet-built

Status: **accepted**

## Related code

- `src/real/exists.py` — built and wired
- `src/future/ranking.py` — to be created in V1.7 (GAP-048)
- `src/alt/neo4j_client.py` — runner-up; not built (V2 swap target)
"""


def test_per_line_deferral_exempts_only_marked_lines(tmp_path: Path) -> None:
    _write(_adr_dir(tmp_path) / "ADR-093-x.md", MIXED_SECTION)
    info = parse_adr(_adr_dir(tmp_path) / "ADR-093-x.md")
    assert info.related_code is not None
    # All three paths parsed; only the un-marked one is "required".
    assert set(info.related_code.files) == {
        "src/real/exists.py",
        "src/future/ranking.py",
        "src/alt/neo4j_client.py",
    }
    assert info.related_code.required_files == ["src/real/exists.py"]

    # Built file absent → the one required file is flagged; deferred ones are not.
    v_missing = check_adr_related_code(tmp_path)
    assert len(v_missing) == 1
    assert "src/real/exists.py" in v_missing[0].message

    # Create the built file → clean (deferred lines never count).
    _write(tmp_path / "src" / "real" / "exists.py", "# x\n")
    assert check_adr_related_code(tmp_path) == []


def test_format_b_existence_enforced(tmp_path: Path) -> None:
    _write(_adr_dir(tmp_path) / "ADR-096-x.md", FORMAT_B_ACCEPTED)
    # Missing → 1 violation.
    assert len(check_adr_related_code(tmp_path)) == 1
    _write(tmp_path / "src" / "synthetic" / "frontmatter.py", "# x\n")
    assert check_adr_related_code(tmp_path) == []
