"""Grow the *private* real-text alias gold from a real Reddit dump.

Output contains verbatim third-party posts, so it defaults to the git-ignored
`evals/gold/private/` directory and must never be committed. The tracked, public
`evals/gold/alias_mentions.jsonl` is derived from it by
`evals/build_public_alias_gold.py` (surface forms kept, prose discarded).

Strategy (non-circular w.r.t. the matcher under eval):
- Labels use **exact case-insensitive substring** match against canonical
  aliases (deterministic).
- The matcher under eval uses `rapidfuzz.fuzz.partial_ratio` (fuzzy) plus a
  short-alias whole-word check. Different signal → not circular.
- Pick texts with exactly **one** distinct school match (no multi-school
  ambiguity) so the gold's `expected_canonical_id` is unambiguous.
- Cap per-canonical to avoid overweighting one school.
- Inject negative cases (texts with zero canonical-alias hits) at ratio
  `neg_ratio`.

Run: `python -m evals.build_alias_gold <posts.jsonl> [--per-canonical N]
[--negatives M] [--out evals/gold/private/alias_mentions.real.jsonl]`.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

from src.er.canonical_index import CanonicalIndex

_DEFAULT_SQLITE = Path("data/sqlite/store.db")
_DEFAULT_GOLD = Path(__file__).parent / "gold" / "private" / "alias_mentions.real.jsonl"


def _compile_alias_patterns(
    aliases: dict[str, str],
    *,
    short_alias_max: int = 5,
) -> list[tuple[str, str, re.Pattern[str]]]:
    """Compile per-alias regex. Short aliases require word boundaries."""

    patterns: list[tuple[str, str, re.Pattern[str]]] = []
    for alias, canonical_id in aliases.items():
        if len(alias) < 2:
            continue
        if len(alias) <= short_alias_max:
            pat = re.compile(rf"\b{re.escape(alias)}\b", re.IGNORECASE)
        else:
            pat = re.compile(re.escape(alias), re.IGNORECASE)
        patterns.append((alias, canonical_id, pat))
    return patterns


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _extract_text(post: dict[str, object]) -> str:
    title = str(post.get("title") or "").strip()
    body = str(post.get("selftext") or post.get("body") or "").strip()
    if title and body:
        return f"{title}\n\n{body}"
    return title or body


def _classify(
    text: str,
    patterns: list[tuple[str, str, re.Pattern[str]]],
) -> set[str]:
    """Return the set of canonical_ids whose alias appears in text."""

    hits: set[str] = set()
    for _, canonical_id, pat in patterns:
        if pat.search(text):
            hits.add(canonical_id)
    return hits


def _existing_texts(gold_path: Path) -> set[str]:
    if not gold_path.is_file():
        return set()
    out: set[str] = set()
    for raw in gold_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        out.add(str(obj.get("text", "")))
    return out


def build(
    *,
    posts_path: Path,
    sqlite_path: Path,
    out_path: Path,
    per_canonical: int,
    negatives: int,
    seed: int,
    min_text_chars: int,
    max_text_chars: int,
) -> tuple[int, int]:
    idx = CanonicalIndex(sqlite_path=sqlite_path)
    if idx.alias_count() == 0:
        print("[err] alias universe empty — ingest L1 first", file=sys.stderr)
        return 0, 0
    patterns = _compile_alias_patterns(idx.aliases())

    rng = random.Random(seed)
    posts = _read_jsonl(posts_path)
    rng.shuffle(posts)

    existing = _existing_texts(out_path)
    per_canon_count: dict[str, int] = defaultdict(int)
    positives: list[dict[str, object]] = []
    neg_candidates: list[str] = []

    for post in posts:
        text = _extract_text(post)
        if not text or len(text) < min_text_chars:
            continue
        if len(text) > max_text_chars:
            text = text[:max_text_chars].rsplit(" ", 1)[0] + "…"
        if text in existing:
            continue

        hits = _classify(text, patterns)
        if not hits:
            if len(neg_candidates) < negatives * 3:
                neg_candidates.append(text)
            continue
        if len(hits) != 1:
            continue   # ambiguous — skip
        canonical_id = next(iter(hits))
        if per_canon_count[canonical_id] >= per_canonical:
            continue
        per_canon_count[canonical_id] += 1
        positives.append({
            "text": text,
            "expected_canonical_id": canonical_id,
            "note": "real-reddit, single-school exact-substring match",
        })
        existing.add(text)

    rng.shuffle(neg_candidates)
    neg_entries = [
        {
            "text": text,
            "expected_canonical_id": None,
            "note": "real-reddit, zero canonical aliases",
        }
        for text in neg_candidates[:negatives]
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as fh:
        for entry in positives + neg_entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return len(positives), len(neg_entries)


_STOPWORDS = {"of", "the", "and", "at", "for", "in", "school", "college", "university"}

# ADEA spreadsheets carry aggregate/summary rows ("Mean of non-zero entries",
# "Total (excluding new schools)") that the L1 adapter mis-ingests as schools
# (GAP-056). Exclude them from the gold so we test real entities, not artifacts.
_AGG_MARKERS = (
    "non-zero", "excluding", "total", "mean", "median", "average",
    "all schools", "number of", "sum of",
)


def _is_aggregate(name: str) -> bool:
    low = name.lower()
    return any(m in low for m in _AGG_MARKERS)


def _canonical_names(aliases: dict[str, str]) -> dict[str, str]:
    """Pick the longest alias per canonical_id as its display name."""
    best: dict[str, str] = {}
    for alias, cid in aliases.items():
        if cid not in best or len(alias) > len(best[cid]):
            best[cid] = alias
    return best


def _misspell(text: str, rng: random.Random) -> str:
    """One deterministic edit: transpose an adjacent letter pair, or drop a letter."""
    chars = list(text)
    letter_positions = [i for i, c in enumerate(chars) if c.isalpha()]
    if len(letter_positions) < 4:
        return text
    if rng.random() < 0.5:
        i = rng.choice(letter_positions[:-1])
        chars[i], chars[i + 1] = chars[i + 1], chars[i]
    else:
        i = rng.choice(letter_positions[1:-1])
        del chars[i]
    return "".join(chars)


def _acronym(name: str) -> str | None:
    words = [w for w in re.split(r"[\s,]+", name) if w and w.lower() not in _STOPWORDS]
    letters = [w[0].upper() for w in words if w[:1].isalpha()]
    return "".join(letters) if len(letters) >= 3 else None


def build_adversarial(
    *, sqlite_path: Path, out_path: Path, seed: int, per_type: int,
) -> dict[str, int]:
    """Generate adversarial gold from REAL canonical aliases (non-circular: the
    matcher is fuzzy `partial_ratio`; perturbations are deterministic edits).

    Types: misspelling (recall under fuzz), abbreviation (acronym recall),
    substring-trap + common-word-trap + over-perturbed garble (precision),
    two-school ambiguity (HITL borderline). Expected outcomes reflect what a
    correct matcher SHOULD do — F1 < 1.0 here is real signal, not a defect.
    """

    idx = CanonicalIndex(sqlite_path=sqlite_path)
    if idx.alias_count() == 0:
        print("[err] alias universe empty — ingest L1 first", file=sys.stderr)
        return {}
    aliases = idx.aliases()
    names = {cid: n for cid, n in _canonical_names(aliases).items() if not _is_aggregate(n)}
    rng = random.Random(seed)

    long_names = sorted((cid, n) for cid, n in names.items() if len(n) >= 10)
    rng.shuffle(long_names)
    short_aliases = sorted(a for a in aliases if 2 <= len(a) <= 6)
    rng.shuffle(short_aliases)

    entries: list[dict[str, object]] = []

    # 1. Misspelling positives (fuzzy recall): a correct matcher SHOULD still hit.
    for cid, name in long_names[:per_type]:
        mis = _misspell(name, rng)
        if mis != name:
            entries.append({"text": f"applying to {mis} this cycle", "expected_canonical_id": cid,
                            "note": "adversarial: 1-edit misspelling"})

    # 2. Abbreviation positives (acronym recall — hard; matcher does no expansion).
    for cid, name in long_names[per_type:per_type * 2]:
        ac = _acronym(name)
        if ac and ac.lower() not in {a.lower() for a in aliases}:
            entries.append({"text": f"got into {ac} dental!", "expected_canonical_id": cid,
                            "note": "adversarial: acronym not in alias list"})

    # 3. Substring-trap negatives: alias embedded in a longer token (no boundary).
    for alias in short_aliases[:per_type]:
        trap = f"x{alias}xz"
        entries.append({"text": f"my {trap} config broke today", "expected_canonical_id": None,
                        "note": "adversarial: substring without word boundary"})

    # 4. Two-school ambiguity (HITL borderline): two distinct aliases in one text.
    distinct = [(cid, n) for cid, n in long_names if len(n) >= 12]
    for k in range(0, min(per_type, len(distinct) - 1), 2):
        (_, n1), (_, n2) = distinct[k], distinct[k + 1]
        entries.append({"text": f"deciding between {n1} and {n2}", "expected_canonical_id": None,
                        "note": "adversarial: two-school ambiguity — auto-accept should abstain"})

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write("# Adversarial alias gold (GAP-044) — generated by build_alias_gold --adversarial\n")
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    counts: dict[str, int] = defaultdict(int)
    for e in entries:
        counts[str(e["note"]).split(":")[1].strip().split(" ")[0]] += 1
    return dict(counts)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="evals.build_alias_gold")
    p.add_argument("posts_path", type=Path, nargs="?", help="Reddit posts JSONL.")
    p.add_argument("--sqlite", type=Path, default=_DEFAULT_SQLITE)
    p.add_argument("--out", type=Path, default=_DEFAULT_GOLD)
    p.add_argument("--per-canonical", type=int, default=3)
    p.add_argument("--negatives", type=int, default=20)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--min-text-chars", type=int, default=40)
    p.add_argument("--max-text-chars", type=int, default=400)
    p.add_argument("--adversarial", action="store_true",
                   help="Generate adversarial gold from canonical aliases (no posts file).")
    p.add_argument("--per-type", type=int, default=40)
    args = p.parse_args(argv)

    if args.adversarial:
        if not args.sqlite.is_file():
            print(f"[err] sqlite not found: {args.sqlite}", file=sys.stderr)
            return 2
        out = (
            args.out if args.out != _DEFAULT_GOLD
            else _DEFAULT_GOLD.parent.parent / "alias_mentions_adversarial.jsonl"
        )
        counts = build_adversarial(
            sqlite_path=args.sqlite, out_path=out,
            seed=args.seed, per_type=args.per_type,
        )
        print(f"adversarial gold -> {out}: {counts}")
        return 0

    if args.posts_path is None or not args.posts_path.is_file():
        print(f"[err] not a file: {args.posts_path}", file=sys.stderr)
        return 2
    if not args.sqlite.is_file():
        print(f"[err] sqlite not found: {args.sqlite}", file=sys.stderr)
        return 2

    pos, neg = build(
        posts_path=args.posts_path, sqlite_path=args.sqlite,
        out_path=args.out, per_canonical=args.per_canonical,
        negatives=args.negatives, seed=args.seed,
        min_text_chars=args.min_text_chars,
        max_text_chars=args.max_text_chars,
    )
    print(f"appended positives={pos} negatives={neg} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
