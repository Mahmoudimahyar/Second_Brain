"""Config-key parser: emits `ConfigKey` nodes from `.env.example` and `pyproject.toml` `[project]`.

For `.env.example`: each `KEY=value` line becomes a ConfigKey. Comments above the line (until the
last blank line) become the description. Required vs optional is heuristic — if the value is
empty and the comment doesn't say "optional", it's required.

For `pyproject.toml`: emits ConfigKeys for entries under `[project]` (top-level metadata) +
`[project.scripts]` (entry points). Dependencies are not emitted individually.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from tools.graphrag.parsers._util import hash_text
from tools.graphrag.types import Node, NodeType, ParseResult

ACCEPTS: tuple[str, ...] = (".env.example", "pyproject.toml")

_ENV_LINE_RE = re.compile(r"^(?P<key>[A-Z_][A-Z0-9_]*)\s*=\s*(?P<value>.*?)\s*$")


def _parse_env_example(text: str, repo_relative: str) -> list[Node]:
    nodes: list[Node] = []
    pending_comments: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            pending_comments.clear()
            continue
        if stripped.startswith("#"):
            pending_comments.append(stripped.lstrip("# ").rstrip())
            continue
        match = _ENV_LINE_RE.match(line)
        if not match:
            pending_comments.clear()
            continue
        key = match.group("key")
        value = match.group("value")
        description = " ".join(pending_comments).strip()
        is_required = value == "" and not any("optional" in c.lower() for c in pending_comments)
        nodes.append(
            Node(
                id=f"cfg:{key}",
                node_type=NodeType.CONFIG_KEY,
                source_path=repo_relative,
                content_hash=hash_text(f"{key}={value}"),
                properties={
                    "key": key,
                    "default_value": value,
                    "description": description,
                    "required": is_required,
                    "source_kind": "env",
                },
            )
        )
        pending_comments.clear()
    return nodes


def _parse_pyproject(text: str, repo_relative: str) -> list[Node]:
    nodes: list[Node] = []
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return nodes
    project = data.get("project")
    if not isinstance(project, dict):
        return nodes
    for k, v in project.items():
        if isinstance(v, (dict, list)) and k not in {"dependencies", "optional-dependencies", "scripts", "entry-points"}:
            continue
        nodes.append(
            Node(
                id=f"cfg:pyproject:{k}",
                node_type=NodeType.CONFIG_KEY,
                source_path=repo_relative,
                content_hash=hash_text(str(v)),
                properties={
                    "key": k,
                    "default_value": str(v) if not isinstance(v, (list, dict)) else None,
                    "description": f"pyproject.toml [project].{k}",
                    "required": k in {"name", "version", "requires-python"},
                    "source_kind": "pyproject",
                },
            )
        )
    scripts = project.get("scripts", {})
    if isinstance(scripts, dict):
        for name, target in scripts.items():
            nodes.append(
                Node(
                    id=f"cfg:pyproject:scripts:{name}",
                    node_type=NodeType.CONFIG_KEY,
                    source_path=repo_relative,
                    content_hash=hash_text(f"{name}={target}"),
                    properties={
                        "key": name,
                        "default_value": str(target),
                        "description": f"pyproject.toml [project.scripts].{name}",
                        "required": False,
                        "source_kind": "pyproject_script",
                    },
                )
            )
    return nodes


def parse(file_path: Path, repo_root: Path) -> ParseResult:
    text = file_path.read_text(encoding="utf-8")
    repo_relative = file_path.relative_to(repo_root).as_posix()
    name = file_path.name
    if name == ".env.example":
        return ParseResult(nodes=_parse_env_example(text, repo_relative))
    if name == "pyproject.toml":
        return ParseResult(nodes=_parse_pyproject(text, repo_relative))
    return ParseResult()
