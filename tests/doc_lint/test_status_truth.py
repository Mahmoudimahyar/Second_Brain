"""WP1 doc-lint — check B: status-truth.

A "Locked"/done claim in a non-negotiable or the tech-stack "Locked" table must
not assert a capability that `implementation-status.md` marks below `Wired`
without a target / not-yet-enforced caveat. Auto-lifts per capability once its
status row reaches `Wired`/`Validated`.
"""

from __future__ import annotations

from pathlib import Path

from tools.doc_lint.check_status_truth import (
    ClaimGuard,
    below_wired_gaps,
    check_status_truth_claims,
    parse_status_rows,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _status(widget_actual: str) -> str:
    return (
        "# Implementation Status\n\n"
        "| Capability | ADR | Doc says | **Actual** | Wiring site / gap |\n"
        "|---|---|---|---|---|\n"
        f"| Widget ranking | ADR-077 | \"Locked\" | {widget_actual} | -> GAP-077. |\n"
        "| Vendor lock | ADR-011 | enforced | **Validated** | src/gateway. |\n"
    )


GUARD = (ClaimGuard("GAP-077", ("widget ranking",), ("docs/nn.md",)),)


def test_parse_status_rows_finds_table() -> None:
    rows = parse_status_rows(_status("**Decided only**"))
    caps = [r.cells[0] for r in rows]
    assert caps == ["Widget ranking", "Vendor lock"]


def test_below_wired_classification() -> None:
    rows = parse_status_rows(_status("**Decided only**"))
    by_cap = {r.cells[0]: r for r in rows}
    assert by_cap["Widget ranking"].below_wired is True
    assert by_cap["Vendor lock"].below_wired is False


def test_below_wired_gaps_excludes_validated() -> None:
    assert below_wired_gaps(parse_status_rows(_status("**Decided only**"))) == {"GAP-077"}
    # When the widget row reaches Validated, its gap is no longer "active".
    assert below_wired_gaps(parse_status_rows(_status("**Validated**"))) == set()


def test_uncaveated_locked_claim_flagged(tmp_path: Path) -> None:
    _write(tmp_path / "status.md", _status("**Decided only**"))
    _write(tmp_path / "docs" / "nn.md", "Widget ranking is **Locked** and shipping.\n")
    v = check_status_truth_claims(tmp_path, status_path=tmp_path / "status.md", guards=GUARD)
    assert len(v) == 1
    assert v[0].kind == "status_truth"
    assert "GAP-077" in v[0].message


def test_caveated_locked_claim_passes(tmp_path: Path) -> None:
    _write(tmp_path / "status.md", _status("**Decided only**"))
    _write(
        tmp_path / "docs" / "nn.md",
        "Widget ranking is **Locked** (target — not yet enforced; GAP-077).\n",
    )
    assert check_status_truth_claims(tmp_path, status_path=tmp_path / "status.md", guards=GUARD) == []


def test_auto_lifts_when_capability_wired(tmp_path: Path) -> None:
    # Uncaveated "Locked" claim, but the capability is now Validated → legitimate.
    _write(tmp_path / "status.md", _status("**Validated**"))
    _write(tmp_path / "docs" / "nn.md", "Widget ranking is **Locked** and done.\n")
    assert check_status_truth_claims(tmp_path, status_path=tmp_path / "status.md", guards=GUARD) == []


def test_no_strong_token_no_violation(tmp_path: Path) -> None:
    _write(tmp_path / "status.md", _status("**Decided only**"))
    # Mentions the anchor but makes no Locked/done claim → fine.
    _write(tmp_path / "docs" / "nn.md", "Widget ranking is planned for a later slice.\n")
    assert check_status_truth_claims(tmp_path, status_path=tmp_path / "status.md", guards=GUARD) == []
