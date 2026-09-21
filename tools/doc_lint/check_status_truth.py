"""Doc↔code truth checker (V1.7 WP1).

Run as ``python -m tools.doc_lint.check_status_truth``. Exits non-zero if any
guardrail is violated, so it can gate CI / the validation suite.

Checks (added incrementally across WP1 sub-steps):

- **A — ADR related-code existence** (``--check-adr-related-code``): an ADR with
  ``Status: accepted`` must have every file listed in its ``## Related code``
  section present on disk — UNLESS the section heading is explicitly marked
  deferred (``(to be created in V1.7 …)``, ``(spike …)``). This is the GAP-050
  guard: ADR-007 shipped ``accepted`` while naming three files that never
  existed.

Checks B (status-truth) and C (stub-wiring) are added in later WP1 sub-steps.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RelatedCodeEntry:
    """One backtick-quoted path from a Related-code section, plus whether the
    line carrying it is marked deferred (``(to be created …)`` / ``GAP-0NN`` /
    ``runner-up`` / ``not built`` …)."""

    path: str
    deferred: bool


@dataclass(frozen=True)
class RelatedCodeSection:
    """A parsed ``## Related code`` section of an ADR."""

    heading: str
    deferred: bool  # section-level: the heading itself carries a deferral marker
    entries: tuple[RelatedCodeEntry, ...] = ()

    @property
    def files(self) -> list[str]:
        """Every referenced path (built or deferred)."""
        return [e.path for e in self.entries]

    @property
    def required_files(self) -> list[str]:
        """Paths whose on-disk existence the lint enforces.

        Empty when the whole section is deferred; otherwise excludes lines
        individually marked deferred.
        """
        if self.deferred:
            return []
        return [e.path for e in self.entries if not e.deferred]


@dataclass(frozen=True)
class AdrInfo:
    """The fields of an ADR the doc-lint cares about."""

    path: Path
    number: int | None
    status: str
    title: str
    related_code: RelatedCodeSection | None

    @property
    def label(self) -> str:
        return f"ADR-{self.number:03d}" if self.number is not None else self.path.stem


@dataclass(frozen=True)
class Violation:
    """A single doc-lint failure."""

    kind: str  # "adr_related_code" | "status_truth" | "stub_wiring"
    location: str
    message: str


# --------------------------------------------------------------------------
# Parsing helpers
# --------------------------------------------------------------------------

# A Related-code heading OR an individual bullet is "deferred" (the file is
# honestly not-yet-built / not-in-repo) when it carries one of these markers.
# This lets an ADR keep built + not-yet-built files in one section: the built
# ones are existence-checked, the marked ones are exempt. Keep this set small
# and visible so a marker always means "a reader can see this isn't built yet".
_DEFER_RE = re.compile(
    r"(to be created|to be created/changed|not built|not yet built|not-yet-built|"
    r"runner-up|\bspike\b|deferred|created at runtime|runtime dir|created when|"
    r"wired in v1\.7|changed/wired|GAP-0\d{2})",
    re.IGNORECASE,
)

_BACKTICK_RE = re.compile(r"`([^`]+)`")

# After stripping a trailing ``:symbol`` / ``:line``, a real repo path token.
_PATHISH_RE = re.compile(r"^[A-Za-z0-9_./*\-]+$")

_RELATED_CODE_HEADING_RE = re.compile(r"^##\s+Related\s+code\b(.*)$", re.IGNORECASE)


def _frontmatter(text: str) -> dict[str, str] | None:
    """Parse a leading ``---`` YAML frontmatter block into a flat dict.

    Deliberately tiny: only top-level ``key: value`` scalar lines (the shape
    ADR-012..020 use). Indented / list lines (e.g. ``revision_history``) are
    skipped — we only need ``status`` and ``adr``.
    """

    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    end: int | None = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None
    fm: dict[str, str] = {}
    for line in lines[1:end]:
        if not line or line[0] in " \t-":
            continue
        key, sep, val = line.partition(":")
        if sep:
            fm[key.strip().lower()] = val.strip()
    return fm


def _extract_status(text: str) -> str:
    """Return the lowercased status word (``accepted`` / ``proposed`` / …)."""

    fm = _frontmatter(text)
    if fm is not None and fm.get("status"):
        return fm["status"].split()[0].strip().lower()
    m = re.search(r"^Status:\s*(.+)$", text, re.MULTILINE)
    if m:
        words = m.group(1).replace("*", " ").split()
        if words:
            return words[0].strip().lower()
    return "unknown"


def _extract_number(path: Path, text: str) -> int | None:
    m = re.search(r"ADR-(\d+)", path.name)
    if m:
        return int(m.group(1))
    fm = _frontmatter(text)
    if fm is not None and fm.get("adr", "").strip().isdigit():
        return int(fm["adr"].strip())
    m = re.search(r"ADR-(\d+)", text)
    return int(m.group(1)) if m else None


def _extract_title(text: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _normalize_path_token(raw: str) -> str | None:
    """Turn a backtick span into a repo-relative path, or ``None`` if it is not
    a path (e.g. a code token like ``ConflictResolver(judge=…)``)."""

    head = raw.split(":", 1)[0].strip()
    if "/" not in head:
        return None
    if not _PATHISH_RE.match(head):
        return None
    return head


def _path_tokens(section_body: str) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for m in _BACKTICK_RE.finditer(section_body):
        tok = _normalize_path_token(m.group(1).strip())
        if tok and tok not in seen:
            seen.add(tok)
            tokens.append(tok)
    return tokens


def _extract_related_code(text: str) -> RelatedCodeSection | None:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not _RELATED_CODE_HEADING_RE.match(line):
            continue
        entries: list[RelatedCodeEntry] = []
        seen: set[str] = set()
        for j in range(i + 1, len(lines)):
            body_line = lines[j]
            if body_line.startswith("## "):
                break
            line_deferred = bool(_DEFER_RE.search(body_line))
            for tok in _path_tokens(body_line):
                if tok in seen:
                    continue
                seen.add(tok)
                entries.append(RelatedCodeEntry(path=tok, deferred=line_deferred))
        return RelatedCodeSection(
            heading=line,
            deferred=bool(_DEFER_RE.search(line)),
            entries=tuple(entries),
        )
    return None


def parse_adr(path: Path, text: str | None = None) -> AdrInfo:
    raw = text if text is not None else path.read_text(encoding="utf-8")
    return AdrInfo(
        path=path,
        number=_extract_number(path, raw),
        status=_extract_status(raw),
        title=_extract_title(raw),
        related_code=_extract_related_code(raw),
    )


# --------------------------------------------------------------------------
# Check A — ADR related-code existence
# --------------------------------------------------------------------------


def _token_exists(repo_root: Path, token: str) -> bool:
    if "*" in token:
        return any(repo_root.glob(token))
    target = repo_root / token
    if token.endswith("/"):
        return target.is_dir()
    return target.exists()


def iter_adrs(adr_dir: Path) -> list[AdrInfo]:
    return [parse_adr(p) for p in sorted(adr_dir.glob("ADR-*.md"))]


def check_adr_related_code(
    repo_root: Path, adr_dir: Path | None = None
) -> list[Violation]:
    """Check A: accepted ADRs' uncaveated Related-code files must exist."""

    adr_dir = adr_dir if adr_dir is not None else repo_root / "docs" / "11-decisions"
    violations: list[Violation] = []
    if not adr_dir.is_dir():
        return violations
    for info in iter_adrs(adr_dir):
        if info.status != "accepted":
            continue
        rc = info.related_code
        if rc is None:
            continue
        for token in rc.required_files:
            if not _token_exists(repo_root, token):
                violations.append(
                    Violation(
                        kind="adr_related_code",
                        location=info.path.name,
                        message=(
                            f"{info.label} is accepted but its Related-code file "
                            f"does not exist: {token} "
                            f"(create it, or mark the section deferred per ADR-021)."
                        ),
                    )
                )
    return violations


# --------------------------------------------------------------------------
# Check C — stub wiring (ConflictResolver with no judge/web-verifier)
# --------------------------------------------------------------------------

# Known stub-wiring sites, keyed ``<relpath>:<enclosing def>``. Each entry is an
# acknowledged not-yet-wired construction that the Wiring Gate (AGENTS.md) treats
# as a GAP, not a completion. **This set MUST be empty by the end of WP3** — once
# the real path constructs the resolver WITH the judge + web-verifier (GAP-052 /
# ADR-024), delete the entry (a stale entry is itself reported).
# Emptied in WP3.4: `reconcile_demo` + the Pass-4 flow now construct
# `ConflictResolver(judge=…, web_verifier=…)`. Any future bare `ConflictResolver()`
# in non-test `src/` is a violation — re-add an entry here only with a reason.
_STUB_WIRING_ALLOWLIST: frozenset[str] = frozenset()


def _enclosing_def(lines: list[str], line_index: int) -> str:
    for k in range(min(line_index, len(lines) - 1), -1, -1):
        m = re.match(r"^\s*(?:async\s+)?def\s+(\w+)", lines[k])
        if m:
            return m.group(1)
    return "<module>"


def find_constructor_calls(text: str, callee: str) -> list[tuple[int, str]]:
    """Return ``(1-based line, arg-string)`` for each ``callee(...)`` call.

    Paren-balanced, so multi-line constructor calls are captured whole. Skips
    matches where ``callee`` is a suffix of a longer identifier.
    """

    needle = callee + "("
    results: list[tuple[int, str]] = []
    i = 0
    while True:
        j = text.find(needle, i)
        if j == -1:
            break
        if j > 0 and (text[j - 1].isalnum() or text[j - 1] == "_"):
            i = j + len(needle)
            continue
        arg_start = j + len(needle)
        depth = 1
        k = arg_start
        while k < len(text) and depth > 0:
            ch = text[k]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            k += 1
        results.append((text.count("\n", 0, j) + 1, text[arg_start : k - 1]))
        i = k
    return results


@dataclass(frozen=True)
class WiringSite:
    """A ConflictResolver construction found in non-test ``src/``."""

    location: str  # relpath:line (def)
    key: str  # relpath:def — the allowlist key
    wired: bool  # judge or web_verifier passed
    allowlisted: bool


def _is_test_path(relpath: str) -> bool:
    return relpath.startswith("tests/") or "/tests/" in f"/{relpath}"


def _find_resolver_calls(text: str) -> list[tuple[int, set[str]]]:
    """AST-based: ``(1-based line, keyword-arg names)`` per ``ConflictResolver(...)``
    call. Uses the parse tree, so mentions inside strings/comments/docstrings are
    ignored (the regex scanner can't tell those apart)."""

    try:
        tree = ast.parse(text)
    except SyntaxError:  # pragma: no cover - source under lint always parses
        return []
    out: list[tuple[int, set[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else (
            func.attr if isinstance(func, ast.Attribute) else None
        )
        if name == "ConflictResolver":
            out.append((node.lineno, {kw.arg for kw in node.keywords if kw.arg}))
    return out


def find_wiring_sites(
    repo_root: Path,
    src_dir: Path | None = None,
    allowlist: frozenset[str] | None = None,
) -> list[WiringSite]:
    src_dir = src_dir if src_dir is not None else repo_root / "src"
    allowlist = allowlist if allowlist is not None else _STUB_WIRING_ALLOWLIST
    sites: list[WiringSite] = []
    if not src_dir.is_dir():
        return sites
    for py in sorted(src_dir.rglob("*.py")):
        rel = py.relative_to(repo_root).as_posix()
        if _is_test_path(rel):
            continue
        text = py.read_text(encoding="utf-8")
        if "ConflictResolver(" not in text:
            continue
        lines = text.splitlines()
        for lineno, kwargs in _find_resolver_calls(text):
            func = _enclosing_def(lines, lineno - 1)
            key = f"{rel}:{func}"
            sites.append(
                WiringSite(
                    location=f"{rel}:{lineno} ({func})",
                    key=key,
                    wired=("judge" in kwargs or "web_verifier" in kwargs),
                    allowlisted=key in allowlist,
                )
            )
    return sites


def check_stub_wiring(
    repo_root: Path,
    src_dir: Path | None = None,
    allowlist: frozenset[str] | None = None,
) -> list[Violation]:
    """Check C: a ConflictResolver built with no judge/web-verifier is stub
    wiring (= a GAP, not done) unless explicitly allowlisted."""

    violations: list[Violation] = []
    for site in find_wiring_sites(repo_root, src_dir=src_dir, allowlist=allowlist):
        if site.wired or site.allowlisted:
            continue
        violations.append(
            Violation(
                kind="stub_wiring",
                location=site.location,
                message=(
                    "ConflictResolver(...) constructed with no judge/web_verifier "
                    "(stub wiring = not done per the Wiring Gate). Pass judge + "
                    "web_verifier (ADR-024 / GAP-052), or allowlist with a reason."
                ),
            )
        )
    return violations


# --------------------------------------------------------------------------
# Check B — status truth (no "Locked/done" claim for a below-Wired capability
#           without a target/not-yet-enforced caveat)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class StatusRow:
    """One row of the `implementation-status.md` 'Current status' table."""

    cells: tuple[str, ...]

    @property
    def raw(self) -> str:
        return " | ".join(self.cells)

    @property
    def actual(self) -> str:
        # Column order: Capability | ADR | Doc says | **Actual** | Wiring/gap
        return self.cells[3] if len(self.cells) > 3 else ""

    @property
    def below_wired(self) -> bool:
        token = re.sub(r"[*`]", "", self.actual).strip().lower()
        head = re.split(r"[\s(,/—-]", token, maxsplit=1)[0] if token else ""
        return head not in {"wired", "validated"}


def parse_status_rows(text: str) -> list[StatusRow]:
    """Parse the main status table (the one whose header has 'Actual')."""

    rows: list[StatusRow] = []
    in_table = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            in_table = False
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        norm = [re.sub(r"[*`]", "", c).strip().lower() for c in cells]
        if "actual" in norm and "capability" in norm:
            in_table = True
            continue
        if set(stripped) <= {"|", "-", ":", " "}:  # separator row
            continue
        if in_table and len(cells) >= 4:
            rows.append(StatusRow(cells=tuple(cells)))
    return rows


def below_wired_gaps(rows: list[StatusRow]) -> set[str]:
    gaps: set[str] = set()
    for row in rows:
        if row.below_wired:
            gaps.update(re.findall(r"GAP-0\d{2}", row.raw))
    return gaps


@dataclass(frozen=True)
class ClaimGuard:
    """If `gap` is still below-Wired, a line in `docs` that names one of
    `anchors` with a strong-claim token and NO caveat is a stale claim."""

    gap: str
    anchors: tuple[str, ...]
    docs: tuple[str, ...]


_STATUS_DOCS = ("docs/01-core/non-negotiables.md", "docs/04-architecture/tech-stack.md")

_CLAIM_GUARDS: tuple[ClaimGuard, ...] = (
    ClaimGuard("GAP-050", ("halo",), _STATUS_DOCS),
    ClaimGuard("GAP-051", ("hybrid retrieval", "hnsw + bm25", "bm25 + hnsw"), _STATUS_DOCS),
    ClaimGuard("GAP-052", ("3-vendor", "three-vendor", "llm-as-judge"), _STATUS_DOCS),
    ClaimGuard("GAP-048", ("ranks by tier first", "tier-first", "ranking_score"), _STATUS_DOCS),
    ClaimGuard("GAP-049", ("signed-graph community",), _STATUS_DOCS),
    ClaimGuard("GAP-053", ("supersede",), _STATUS_DOCS),
)

_STRONG_TOKENS = ("locked", "shipped", "✅", "enforced", "100%")
_CAVEAT_TOKENS = (
    "target", "not yet", "not-yet", "⚠", "not built", "not-built", "not wired",
    "not-wired", "gap-0", "deferred", "decided", "proposed", "spike", "to be",
    "v1.7", "v1.x", "→ adr",
)


def check_status_truth_claims(
    repo_root: Path,
    status_path: Path | None = None,
    guards: tuple[ClaimGuard, ...] = _CLAIM_GUARDS,
) -> list[Violation]:
    """Check B: a 'Locked'/done claim for a below-Wired capability must carry a
    target/not-yet caveat. Auto-lifts per capability once its row moves to
    `Wired`/`Validated` in `implementation-status.md`."""

    status_path = status_path or repo_root / "docs/00-bootstrap/implementation-status.md"
    if not status_path.is_file():
        return []
    active_gaps = below_wired_gaps(parse_status_rows(status_path.read_text(encoding="utf-8")))

    violations: list[Violation] = []
    for guard in guards:
        if guard.gap not in active_gaps:
            continue  # capability is now Wired/Validated — claim is legitimate
        for rel in guard.docs:
            doc = repo_root / rel
            if not doc.is_file():
                continue
            for n, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
                low = line.lower()
                if not any(a in low for a in guard.anchors):
                    continue
                if not any(s in low for s in _STRONG_TOKENS):
                    continue
                if any(c in low for c in _CAVEAT_TOKENS):
                    continue
                violations.append(
                    Violation(
                        kind="status_truth",
                        location=f"{rel}:{n}",
                        message=(
                            f"claims '{_first_strong(low)}' for a capability "
                            f"implementation-status marks below Wired ({guard.gap}); "
                            f"add a target / not-yet-enforced caveat."
                        ),
                    )
                )
    return violations


def _first_strong(low: str) -> str:
    for s in _STRONG_TOKENS:
        if s in low:
            return s
    return "Locked"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def find_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _report(violations: list[Violation]) -> None:
    if not violations:
        print("doc-lint: OK - no violations.")
        return
    by_kind: dict[str, list[Violation]] = {}
    for v in violations:
        by_kind.setdefault(v.kind, []).append(v)
    print(f"doc-lint: {len(violations)} violation(s):\n")
    for kind, items in sorted(by_kind.items()):
        print(f"[{kind}]")
        for v in items:
            print(f"  - {v.location}: {v.message}")
        print()


def _print_wiring_sites(repo_root: Path) -> None:
    sites = find_wiring_sites(repo_root)
    print("ConflictResolver wiring sites (non-test src/):\n")
    if not sites:
        print("  (none found)")
    for s in sites:
        if s.wired:
            tag = "WIRED (judge/web_verifier passed)"
        elif s.allowlisted:
            tag = "STUB (allowlisted - must be empty by end of WP3)"
        else:
            tag = "STUB (NOT allowlisted - VIOLATION)"
        print(f"  - {s.location}: {tag}")
    allow = sorted(_STUB_WIRING_ALLOWLIST)
    print(f"\nStub-wiring allowlist ({len(allow)} entr{'y' if len(allow) == 1 else 'ies'}):")
    for key in allow:
        print(f"  - {key}")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_status_truth",
        description="Doc<->code truth guardrail (V1.7 WP1).",
    )
    parser.add_argument(
        "--check-adr-related-code",
        action="store_true",
        help="Only run check A (ADR Related-code files exist).",
    )
    parser.add_argument(
        "--print-wiring-sites",
        action="store_true",
        help="Print every ConflictResolver construction site + the stub allowlist "
        "(check C). Exits non-zero if an un-allowlisted stub exists.",
    )
    parser.add_argument(
        "--check-status-truth",
        action="store_true",
        help="Only run check B (no stale Locked/done claim for a below-Wired capability).",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repo root (defaults to the SecBrain checkout containing this tool).",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else find_repo_root()

    violations: list[Violation] = []
    if args.print_wiring_sites:
        _print_wiring_sites(repo_root)
        violations += check_stub_wiring(repo_root)
    elif args.check_adr_related_code:
        violations += check_adr_related_code(repo_root)
    elif args.check_status_truth:
        violations += check_status_truth_claims(repo_root)
    else:
        # Default == run every check.
        violations += check_adr_related_code(repo_root)
        violations += check_stub_wiring(repo_root)
        violations += check_status_truth_claims(repo_root)

    _report(violations)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
