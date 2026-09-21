"""Canonical entity index + ambiguity-aware, type-grounded resolution.

Loaded from the SQLite `alias` + `l1_school` tables (populated by the L1 Excel /
DB adapters). Beyond the flat alias→id lookup the Pass-1 matcher uses, this keeps
**all** candidates per alias and resolves ambiguity grounded in the official
record: an alias like "Michigan"/"Penn"/"UT" maps to several official entities
(the dental `school:`, the general/residency `institution:`, sometimes a
different state) — `resolve()` picks by entity type (dental-vs-residency
context), the official `state` field, and a dental-applicant prior, and flags
irreducible ambiguity for HITL instead of silently guessing.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

# Dental-school vs residency-program context cues (decide School vs Institution).
_DENTAL_CTX: frozenset[str] = frozenset({
    "dds", "dmd", "dental school", "predental", "pre-dental", "aadsas",
    "d-school", "dental student", "d1 ", "d2 ", "d3 ", "d4 ", "admitted to dental",
})
_RESIDENCY_CTX: frozenset[str] = frozenset({
    "residency", "pgy", "aegd", "gpr", "omfs", "fellowship", "co-resident",
    "program director", "match list", "matched at", "residency program",
})

# US state name → 2-letter abbrev (schools store the abbrev, institutions the
# full name; normalize both to the abbrev for comparison).
_US_STATES: dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC",
}
_ABBREVS: frozenset[str] = frozenset(_US_STATES.values())

# Generic tokens stripped when matching a dental `school:` to its parent
# `institution:` (so "University of Iowa" ↔ "University of Iowa College of
# Dentistry" bridge on the distinctive token "iowa").
_GENERIC_BASE: frozenset[str] = frozenset({
    "university", "college", "school", "of", "the", "dentistry", "dental",
    "medicine", "medical", "health", "sciences", "science", "center", "centre",
    "hospital", "institute", "and", "at", "in", "program", "graduate",
})


def _distinctive_tokens(name: str) -> frozenset[str]:
    toks = re.findall(r"[a-z0-9]+", (name or "").lower())
    return frozenset(t for t in toks if len(t) >= 3 and t not in _GENERIC_BASE)


@dataclass(frozen=True)
class ResolvedMention:
    """Outcome of disambiguating one alias hit against the official record."""

    canonical_id: str
    canonical_name: str
    confidence: float           # 1.0 unique · 0.85 type · 0.8 state · 0.4 ambiguous
    reason: str
    needs_review: bool


def _state_to_abbrev(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip()
    if v.upper() in _ABBREVS:
        return v.upper()
    return _US_STATES.get(v.lower())


def _states_in_text(text: str) -> set[str]:
    """Abbrevs of any US state named (by full name or abbrev) in `text`."""
    found: set[str] = set()
    low = text.lower()
    for name, abbr in _US_STATES.items():
        if name in low:
            found.add(abbr)
    for abbr in _ABBREVS:
        if re.search(rf"\b{abbr}\b", text):   # abbrevs are case-sensitive (caps)
            found.add(abbr)
    return found


class CanonicalIndex:
    """In-memory alias → canonical entity lookup + type-grounded resolution."""

    def __init__(self, sqlite_path: Path) -> None:
        self._sqlite_path = Path(sqlite_path)
        self._alias_to_canonical: dict[str, str] = {}       # first-wins (back-compat)
        self._alias_to_candidates: dict[str, list[str]] = {}  # all candidates, ordered
        self._canonical_to_name: dict[str, str] = {}
        self._canonical_to_aliases: dict[str, list[str]] = {}
        self._canonical_to_state: dict[str, str | None] = {}
        self._institution_to_school: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        self._alias_to_canonical.clear()
        self._alias_to_candidates.clear()
        self._canonical_to_name.clear()
        self._canonical_to_aliases.clear()
        self._canonical_to_state.clear()
        self._institution_to_school.clear()
        if not self._sqlite_path.is_file():
            return
        conn = sqlite3.connect(self._sqlite_path)
        try:
            for alias_text, canonical_id in conn.execute(
                "SELECT alias_text, canonical_id FROM alias",
            ):
                at, cid = str(alias_text), str(canonical_id)
                self._alias_to_canonical.setdefault(at, cid)
                cands = self._alias_to_candidates.setdefault(at, [])
                if cid not in cands:
                    cands.append(cid)
                self._canonical_to_aliases.setdefault(cid, []).append(at)
            self._load_canonical(conn)
        except sqlite3.OperationalError:
            # Fresh DB without the V1 anchor tables (alias / l1_school):
            # behave as an empty index instead of crashing the caller.
            return
        finally:
            conn.close()
        self._build_sibling_map()

    def _load_canonical(self, conn: sqlite3.Connection) -> None:
        try:
            rows = conn.execute(
                "SELECT canonical_id, canonical_name, state FROM l1_school",
            ).fetchall()
        except sqlite3.OperationalError:  # legacy DB without `state`
            rows = [(c, n, None) for c, n in conn.execute(
                "SELECT canonical_id, canonical_name FROM l1_school")]
        for canonical_id, canonical_name, state in rows:
            self._canonical_to_name[str(canonical_id)] = str(canonical_name)
            self._canonical_to_state[str(canonical_id)] = (
                _state_to_abbrev(state) if state else None
            )

    def _build_sibling_map(self) -> None:
        """Map each residency `institution:` to its sibling dental `school:` by
        distinctive base-university token containment (unique match only)."""
        schools = [
            (cid, _distinctive_tokens(self._canonical_to_name.get(cid, "")))
            for cid in self._canonical_to_name
            if self.entity_type(cid) == "school"
        ]
        for cid in self._canonical_to_name:
            if self.entity_type(cid) != "institution":
                continue
            inst_tok = _distinctive_tokens(self._canonical_to_name.get(cid, ""))
            if not inst_tok:
                continue
            matches = [s for s, stoks in schools if inst_tok <= stoks]
            if len(matches) == 1:
                self._institution_to_school[cid] = matches[0]

    # -- flat lookups (back-compat with the Pass-1 matcher) -------------------

    def aliases(self) -> dict[str, str]:
        return dict(self._alias_to_canonical)

    def candidates(self, alias_text: str) -> list[str]:
        return list(self._alias_to_candidates.get(alias_text, []))

    def canonical_name(self, canonical_id: str) -> str | None:
        return self._canonical_to_name.get(canonical_id)

    def aliases_for(self, canonical_id: str) -> list[str]:
        return list(self._canonical_to_aliases.get(canonical_id, []))

    def entity_type(self, canonical_id: str) -> str:
        return canonical_id.split(":", 1)[0] if ":" in canonical_id else "unknown"

    def state_of(self, canonical_id: str) -> str | None:
        return self._canonical_to_state.get(canonical_id)

    def alias_count(self) -> int:
        return len(self._alias_to_canonical)

    def canonical_count(self) -> int:
        return len(self._canonical_to_name)

    # -- ambiguity-aware resolution -------------------------------------------

    def resolve(
        self, alias_text: str, *, context: str = "", default_type: str = "school",
    ) -> ResolvedMention | None:
        """Resolve an alias hit to a single official entity, grounded in the
        record. Returns None only when the alias is unknown. For an irreducibly
        ambiguous alias it returns the best-prior candidate with
        ``needs_review=True`` (→ LLM-matcher / HITL), never a silent wrong pick.
        """
        cands = self._alias_to_candidates.get(alias_text)
        if not cands:
            return None
        ctx = (context or "").lower()
        dental = any(k in ctx for k in _DENTAL_CTX)
        residency = any(k in ctx for k in _RESIDENCY_CTX)

        if len(cands) == 1:
            cid, conf, reason, review = cands[0], 1.0, "unique", False
        else:
            pref: tuple[str, ...]
            if residency and not dental:
                pref = ("institution", "specialty")
            elif dental and not residency:
                pref = ("school",)
            else:                                    # dental-applicant prior
                pref = (default_type,)
            pool = [c for c in cands if self.entity_type(c) in pref] or list(cands)
            if len(pool) == 1:
                cid, conf, reason, review = pool[0], 0.85, f"type:{pref[0]}", False
            else:
                states = _states_in_text(context)
                by_state = [c for c in pool if self.state_of(c) in states] if states else []
                if len(by_state) == 1:
                    cid, conf, reason, review = by_state[0], 0.8, "state", False
                else:
                    # Irreducible (e.g. UMSD → Maryland/Michigan/Minnesota, no
                    # state): surface the best prior but flag it — never guess.
                    pool = by_state or pool
                    cid, conf, reason, review = pool[0], 0.4, "ambiguous_unresolved", True

        # School↔Institution bridge: in dental (non-residency) context a bare
        # university that landed on the residency `institution:` is redirected to
        # its sibling dental `school:` — the applicant almost always means the
        # dental school. Skipped when the post is clearly residency-focused.
        if not residency and self.entity_type(cid) == "institution":
            sibling = self._institution_to_school.get(cid)
            if sibling is not None:
                cid, reason = sibling, f"{reason}+inst_to_school"

        return self._mk(cid, conf, reason, needs_review=review)

    def _mk(self, cid: str, conf: float, reason: str, *, needs_review: bool) -> ResolvedMention:
        return ResolvedMention(
            canonical_id=cid, canonical_name=self._canonical_to_name.get(cid, cid),
            confidence=conf, reason=reason, needs_review=needs_review,
        )
