"""The generated reference pages must match the code (see tools/docs/gen_reference.py)."""

from __future__ import annotations

from typing import Any

import typer

from tools.docs.gen_reference import OUT_DIR, PAGES, _context, _is_group, main


def test_reference_pages_are_up_to_date() -> None:
    assert main(["--check"]) == 0, "run `python -m tools.docs.gen_reference` and commit the result"


def _leaf_commands(group: Any, prefix: str) -> list[str]:
    out: list[str] = []
    ctx = _context(group)
    for name in group.list_commands(ctx):
        sub = group.get_command(ctx, name)
        if sub is None:
            continue
        if _is_group(sub):
            out.extend(_leaf_commands(sub, f"{prefix} {name}"))
        else:
            out.append(f"{prefix} {name}")
    return out


def test_every_cli_command_is_documented() -> None:
    from src.cli import app  # noqa: PLC0415

    page = (OUT_DIR / "cli.md").read_text(encoding="utf-8")
    root: Any = typer.main.get_command(app)
    assert _is_group(root)          # duck-typed: newer Typer vendors its own click classes

    commands = _leaf_commands(root, "secbrain")
    assert len(commands) >= 20
    missing = [name for name in commands if f"`{name}`" not in page]
    assert not missing, missing
    assert set(PAGES) == {"cli.md", "rest-api.md"}
