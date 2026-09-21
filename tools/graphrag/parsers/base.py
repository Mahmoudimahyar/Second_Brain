"""Base types for repo parsers.

Each parser module exposes:

  - `ACCEPTS: tuple[str, ...]`  — glob patterns matched against repo-relative paths
  - `parse(file_path: Path, repo_root: Path) -> ParseResult`  — pure function

Glob matching:

  - **Path-bearing patterns** (containing `/`) are matched against the full repo-relative path.
    `**` matches any number of path segments; `*` matches within a single segment; `?` matches
    one non-slash character.
  - **Bare patterns** (no `/`, e.g., `*.md`) are matched against the basename only via `fnmatch`.

`RepoParser` is a `Protocol` so parsers don't have to inherit; module-level functions + constants
are enough. The indexer (`tools/graphrag/index.py`) discovers parsers via the registry in
`tools/graphrag/parsers/__init__.py`.
"""

from __future__ import annotations

import fnmatch
import re
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from tools.graphrag.types import ParseResult


class RepoParser(Protocol):
    """Structural contract for a repo-file parser.

    Implementations should be pure: same input → same output. Side effects (writing nodes,
    embeddings, etc.) belong in the indexer, not the parser.
    """

    ACCEPTS: tuple[str, ...]

    def parse(self, file_path: Path, repo_root: Path) -> ParseResult: ...


def accepts_path(parser: RepoParser, repo_relative_path: str) -> bool:
    """True if `repo_relative_path` matches any of `parser.ACCEPTS` glob patterns."""

    normalized = repo_relative_path.replace("\\", "/")
    basename = normalized.rsplit("/", 1)[-1]
    for pattern in parser.ACCEPTS:
        if "/" in pattern:
            if _path_glob(pattern).fullmatch(normalized):
                return True
        elif fnmatch.fnmatchcase(basename, pattern):
            return True
    return False


@lru_cache(maxsize=256)
def _path_glob(pattern: str) -> re.Pattern[str]:
    """Translate a path glob (`/**`/, `**/`, `**`, `*`, `?`) into a compiled regex."""

    parts: list[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        if pattern[i : i + 4] == "/**/":
            parts.append("(?:/.*)??/")
            i += 4
        elif pattern[i : i + 3] == "**/":
            parts.append("(?:.*/)??")
            i += 3
        elif pattern[i : i + 3] == "/**":
            parts.append("(?:/.*)??")
            i += 3
        elif pattern[i : i + 2] == "**":
            parts.append(".*")
            i += 2
        elif pattern[i] == "*":
            parts.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            parts.append("[^/]")
            i += 1
        elif pattern[i] in r".+()[]^$\|{}":
            parts.append("\\" + pattern[i])
            i += 1
        else:
            parts.append(re.escape(pattern[i]) if not pattern[i].isalnum() and pattern[i] != "_" else pattern[i])
            i += 1
    return re.compile("".join(parts))
