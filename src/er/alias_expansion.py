"""Generate short-form aliases from L1 canonical school names.

The L1 source (ADEA Report 2) supplies formal names like
  "New York University, College of Dentistry"
  "University of California, Los Angeles School of Dentistry"
  "Harvard School of Dental Medicine"

Forum posts use abbreviations:
  "NYU", "UCLA", "Harvard"

Pure-rule expansion generates likely surface forms:
  - acronym of the capitalized words            → "NYU", "UCLA"
  - first-comma-prefix                          → "New York University"
  - drop trailing "School of Dental Medicine" / "College of Dentistry" /
    "School of Dentistry"                       → "Harvard", "Tufts"
  - capitalized initialism (first letters)      → "USC", "BU"
  - common abbreviation patterns                → "U of P", "U Penn", "Penn"

Each expansion is emitted as an `alias` row with `alias_source="discovered"`
(distinct from `alias_source="manual"` for the original L1-derived alias).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Words that get stripped to produce a "short name" anchor.
_TAIL_PATTERNS: tuple[str, ...] = (
    "college of dentistry",
    "school of dental medicine",
    "school of dentistry",
    "college of dental medicine",
    "school of medicine",
    "dental school",
    "school of dental medicine and oral health",
    "school of dental and oral health",
)
# Articles + filler words ignored when building the acronym.
_STOPWORDS: frozenset[str] = frozenset({
    "the", "of", "and", "at", "in", "for", "on", "to", "a", "an",
})
# Conservative U-of-X patterns.
_U_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\buniversity of pennsylvania\b", re.I), "Penn"),
    (re.compile(r"\buniversity of pennsylvania\b", re.I), "UPenn"),
    (re.compile(r"\buniversity of pennsylvania\b", re.I), "U of P"),
    (re.compile(r"\buniversity of california,? los angeles\b", re.I), "UCLA"),
    (re.compile(r"\buniversity of california,? san francisco\b", re.I), "UCSF"),
    (re.compile(r"\bnew york university\b", re.I), "NYU"),
    (re.compile(r"\bnorthwestern university\b", re.I), "Northwestern"),
    (re.compile(r"\bharvard\b", re.I), "Harvard"),
    (re.compile(r"\bcolumbia\b", re.I), "Columbia"),
    (re.compile(r"\bboston university\b", re.I), "BU"),
    (re.compile(r"\buniversity of southern california\b", re.I), "USC"),
    (re.compile(r"\buniversity of michigan\b", re.I), "Michigan"),
    (re.compile(r"\bohio state university\b", re.I), "Ohio State"),
    (re.compile(r"\bohio state university\b", re.I), "OSU"),
    (re.compile(r"\buniversity of north carolina\b", re.I), "UNC"),
    (re.compile(r"\bvirginia commonwealth university\b", re.I), "VCU"),
    (re.compile(r"\buniversity of texas\b", re.I), "UT"),
    (re.compile(r"\buniversity of florida\b", re.I), "UF"),
    (re.compile(r"\buniversity of washington\b", re.I), "UW"),
    (re.compile(r"\buniversity of illinois\b", re.I), "UIC"),
    (re.compile(r"\buniversity of minnesota\b", re.I), "UMN"),
    (re.compile(r"\buniversity of detroit mercy\b", re.I), "UDM"),
    (re.compile(r"\bcase western reserve university\b", re.I), "Case"),
    (re.compile(r"\btufts university\b", re.I), "Tufts"),
    (re.compile(r"\buniversity of louisville\b", re.I), "Louisville"),
)


@dataclass(frozen=True)
class ExpandedAlias:
    canonical_id: str
    alias_text: str
    source: str            # "acronym" / "stripped_tail" / "pattern" / "first_phrase"


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-]*")
_EMBEDDED_ACRONYM_RE = re.compile(r"\b([A-Z]{2,5})\b")
_GENERIC_ACRONYMS: frozenset[str] = frozenset({
    "OF", "AT", "THE", "AND", "DDS", "DMD", "BDS", "MS", "PHD",
})
_MIN_ALIAS_LEN: int = 2


def expand_aliases(canonical_id: str, canonical_name: str) -> list[ExpandedAlias]:
    """Return a deduplicated list of short-form aliases for `canonical_name`."""

    if not canonical_name:
        return []
    seen: set[str] = set()
    out: list[ExpandedAlias] = []

    def _add(text: str, source: str) -> None:
        clean = text.strip().strip(",;:")
        if len(clean) < _MIN_ALIAS_LEN:
            return
        key = clean.lower()
        if key in seen:
            return
        seen.add(key)
        out.append(ExpandedAlias(
            canonical_id=canonical_id, alias_text=clean, source=source,
        ))

    # 1. Pattern hits (U-of-X common forms).
    for pat, replacement in _U_PATTERNS:
        if pat.search(canonical_name):
            _add(replacement, "pattern")

    # 2. "X, Y" prefix — take the part before the first comma.
    if "," in canonical_name:
        prefix = canonical_name.split(",", 1)[0]
        _add(prefix, "first_phrase")

    # 3. Drop common tails ("College of Dentistry", etc.).
    lowered = canonical_name.lower()
    for tail in _TAIL_PATTERNS:
        if lowered.endswith(tail):
            short = canonical_name[: -len(tail)].rstrip(", \t")
            _add(short, "stripped_tail")
            break

    # 4. Embedded acronyms (catches "USC" in "Herman Ostrow School of Dentistry of USC").
    # Skipped for ALL-CAPS names: the heuristic relies on an uppercase token
    # standing out amid mixed-case text. DB source names are entirely uppercase
    # ("HIGH POINT UNIVERSITY ..."), so every short word would be mis-read as an
    # acronym ("HIGH"/"POINT"/"STATE"/"ORAL"/"NEW" — measured false positives on
    # the real forum corpus). Genuine acronyms come from the U-of-X patterns +
    # the DB short_name / market_intel aliases instead.
    if not canonical_name.isupper():
        for m in _EMBEDDED_ACRONYM_RE.findall(canonical_name):
            if m in _GENERIC_ACRONYMS:
                continue
            _add(m, "embedded_acronym")

    # 5. Acronym of significant words. Minimum 3 chars: 2-letter word-initial
    # acronyms are both highly ambiguous (e.g. "UM" -> 8 schools) and collide
    # with common English words ("OF"/"OR"/"OP" from residency-specialty names
    # matched "of"/"or"/"op" in forum text — measured false positives on the
    # real corpus). Genuine 2-letter codes (UF, BU, UW) come from the U-of-X
    # patterns (step 1), not from this initials mash-up.
    words = [w for w in _WORD_RE.findall(canonical_name) if w.lower() not in _STOPWORDS]
    if 2 <= len(words) <= 8:
        acronym = "".join(w[0] for w in words).upper()
        if 3 <= len(acronym) <= 6:
            _add(acronym, "acronym")

    return out
