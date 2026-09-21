"""The generated reference pages must match the code (see tools/docs/gen_reference.py)."""

from __future__ import annotations

from tools.docs.gen_reference import OUT_DIR, PAGES, main


def test_reference_pages_are_up_to_date() -> None:
    assert main(["--check"]) == 0, "run `python -m tools.docs.gen_reference` and commit the result"


def test_every_cli_command_is_documented() -> None:
    import click  # noqa: PLC0415
    import typer  # noqa: PLC0415

    from src.cli import app  # noqa: PLC0415

    page = (OUT_DIR / "cli.md").read_text(encoding="utf-8")
    root = typer.main.get_command(app)
    assert isinstance(root, click.Group)

    def names(group: click.Group, prefix: str) -> list[str]:
        out: list[str] = []
        ctx = click.Context(group)
        for name in group.list_commands(ctx):
            sub = group.get_command(ctx, name)
            if isinstance(sub, click.Group):
                out.extend(names(sub, f"{prefix} {name}"))
            elif sub is not None:
                out.append(f"{prefix} {name}")
        return out

    missing = [n for n in names(root, "secbrain") if f"`{n}`" not in page]
    assert not missing, missing
    assert set(PAGES) == {"cli.md", "rest-api.md"}
