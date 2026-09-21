from __future__ import annotations

import re
from dataclasses import dataclass, replace

from rapidfuzz import fuzz

from src.er.canonical_index import CanonicalIndex
from src.er.llm_matcher import MentionLLMMatcher

# Domain-generic tokens that must NOT, on their own, carry a fuzzy match — a
# multi-word alias ("CU Dental") whose only long token is generic ("dental")
# otherwise partial-matches nearly every dental-forum post.
_GENERIC_TOKENS: frozenset[str] = frozenset({
    # institution/role words
    "dental", "dentistry", "school", "college", "university", "medicine",
    "medical", "oral", "health", "center", "centre", "hospital", "institute",
    "program", "programs", "residency", "department", "sciences", "science",
    "clinic", "clinics", "system", "systems", "care", "services", "service",
    "graduate", "academy", "foundation",
    # academic-subject / qualifier words that appear in entity names but are not
    # entity-distinctive (e.g. "Oral Biology" must not match on "biology")
    "biology", "biomedical", "chemistry", "physics", "public", "general",
    "advanced", "education", "practice", "applied", "clinical", "research",
    "studies", "biomechanics", "esthetic", "digital", "operative", "implant",
    "geriatric", "special", "craniofacial", "fellowship", "anesthesiology",
    # generic geography/qualifier
    "greater", "memorial", "regional", "community", "national", "northern",
    "southern", "eastern", "western", "central",
    "the", "and", "for", "of", "at", "in",
})
# A distinctive (non-generic) alias token must fuzzy-appear at least this well.
_DISTINCTIVE_MIN: float = 88.0


def _token_present(token: str, haystack: str) -> bool:
    """Is a distinctive alias token present? Short proper-noun codes
    ("york"/"iowa"/"ohio") match **whole-word** so they don't flood via
    substrings ("miss" inside "missing"/"admission"); longer tokens allow a
    **fuzzy** partial match to keep misspelling recall ("pennsylvania" ~
    "pennsylvana")."""
    if len(token) <= 5:
        return re.search(rf"\b{re.escape(token)}\b", haystack) is not None
    return fuzz.partial_ratio(token, haystack) >= _DISTINCTIVE_MIN


@dataclass(frozen=True)
class Mention:
    """A canonical-entity mention found in free text."""

    canonical_id: str
    canonical_name: str
    matched_alias: str
    score: float                # 0-100 (partial_ratio + token bonus)
    needs_review: bool          # True when score is in the HITL band


class Pass1MentionExtractor:
    """Pass 1 deterministic mention extraction per FR-3 + plan.md.

    Scans free-text against the L1 canonical alias universe using
    `rapidfuzz.fuzz.partial_ratio` (substring fuzzy match) + an exact-token
    sanity check. Each post body + title is scanned once.

    Tiered output (FR-3.1..3.3):
      - score >= auto_accept_threshold (default 90) → emit MENTIONS_SCHOOL edge
      - hitl_lower_threshold <= score < auto_accept → emit with needs_review=True
      - score < hitl_lower_threshold → drop

    The thresholds are slightly lower than the L1 alias matcher's 95 because
    we are matching against arbitrary text where the canonical name is
    embedded; partial_ratio scores are naturally lower than token_set_ratio
    against a clean alias string.
    """

    DEFAULT_AUTO_ACCEPT: float = 90.0
    DEFAULT_HITL_LOWER: float = 75.0
    MIN_ALIAS_LEN: int = 2        # 2-char aliases (BU/UF/UW) use word-boundary match
    SHORT_ALIAS_MAX_LEN: int = 5  # treat aliases ≤ 5 chars as whole-word lookups

    def __init__(
        self,
        index: CanonicalIndex,
        *,
        auto_accept_threshold: float = DEFAULT_AUTO_ACCEPT,
        hitl_lower_threshold: float = DEFAULT_HITL_LOWER,
        llm_matcher: MentionLLMMatcher | None = None,
    ) -> None:
        if not (0 <= hitl_lower_threshold <= auto_accept_threshold <= 100):
            raise ValueError(
                "thresholds must satisfy 0 <= hitl_lower <= auto_accept <= 100",
            )
        self._index = index
        self._auto_accept = auto_accept_threshold
        self._hitl_lower = hitl_lower_threshold
        # ADR-022: optional LLM matcher for the borderline (needs_review) band.
        self._llm_matcher = llm_matcher
        aliases = index.aliases()
        self._aliases: list[str] = [
            a for a in aliases if len(a) >= self.MIN_ALIAS_LEN
        ]
        self._aliases_lower: list[str] = [a.lower() for a in self._aliases]
        self._alias_to_canonical: dict[str, str] = dict(aliases)

    def extract(self, text: str) -> list[Mention]:
        """Return zero or more mentions in `text`. Deduplicated by canonical_id."""

        if not text or not self._aliases:
            return []
        haystack = text.lower()
        best_by_canonical: dict[str, Mention] = {}

        for alias, alias_lower in zip(self._aliases, self._aliases_lower, strict=True):
            # Short aliases (NYU, UCLA, etc.) require an exact whole-word match
            # to avoid spurious substring hits (e.g., "NYU" inside "anyway").
            if len(alias) <= self.SHORT_ALIAS_MAX_LEN:
                # Short aliases (acronyms / proper-name codes: UF, NYU, Penn,
                # Case) are capitalized in real usage — match case-SENSITIVELY
                # against the original text so they don't fire on the lowercase
                # common word ("Case" the school vs "in case", "UF" vs "uf").
                if not re.search(rf"\b{re.escape(alias)}\b", text):
                    continue
                score = 100.0
            else:
                score = float(fuzz.partial_ratio(alias_lower, haystack))
                if score < self._hitl_lower:
                    continue
                # Precision guard: a partial_ratio hit must be carried by a
                # *distinctive* (non-generic) alias token actually appearing.
                # Otherwise a generic word ("dental"/"school"/"university") lets
                # a multi-word alias ("CU Dental") match almost every post
                # (measured: 1033 false "Colorado" hits via "CU Dental").
                distinctive = [
                    t for t in alias_lower.split()
                    if len(t) >= 4 and t not in _GENERIC_TOKENS
                ]
                if distinctive:
                    # Require >=min(2, #distinctive) distinctive tokens to appear:
                    # one common token ("california"/"system"/"island") must not
                    # carry a long multi-word name ("V.A. Northern California
                    # Health Care System Mare Island" flooded 188 posts on one).
                    present = sum(
                        1 for t in distinctive if _token_present(t, haystack)
                    )
                    if present < min(2, len(distinctive)):
                        continue
                # No distinctive token (a short code + generic words only):
                # require the full alias phrase verbatim, not a loose alignment.
                elif not re.search(rf"\b{re.escape(alias_lower)}\b", haystack):
                    continue

            # Ambiguity-aware, type-grounded resolution: an alias like
            # "Michigan"/"Penn"/"UT" maps to several official entities (dental
            # school vs general/residency institution vs another state). resolve()
            # picks by entity type (dental-vs-residency context), the official
            # state field, and a dental-applicant prior — flagging irreducible
            # ambiguity for review instead of silently committing a guess.
            resolved = self._index.resolve(alias, context=text)
            if resolved is None:
                continue
            canonical_id = resolved.canonical_id
            needs_review = score < self._auto_accept or resolved.needs_review
            prior = best_by_canonical.get(canonical_id)
            if prior is not None and prior.score >= score:
                continue
            best_by_canonical[canonical_id] = Mention(
                canonical_id=canonical_id,
                canonical_name=resolved.canonical_name,
                matched_alias=alias,
                score=score,
                needs_review=needs_review,
            )

        return self._apply_llm_fallback(list(best_by_canonical.values()), text)

    def _apply_llm_fallback(self, mentions: list[Mention], text: str) -> list[Mention]:
        """ADR-022: LLM the middle. Auto-accepts pass through; for each borderline
        (needs_review) mention the LLM accepts (clear needs_review), rejects (drop),
        or is undecided (keep needs_review → HITL)."""

        if self._llm_matcher is None:
            return mentions
        resolved: list[Mention] = []
        for m in mentions:
            if not m.needs_review:
                resolved.append(m)
                continue
            verdict = self._llm_matcher.resolve(text, m.canonical_name)
            if verdict is True:
                resolved.append(replace(m, needs_review=False))
            elif verdict is None:
                resolved.append(m)
            # verdict is False → reject (drop the borderline mention)
        return resolved

    @property
    def auto_accept_threshold(self) -> float:
        return self._auto_accept

    @property
    def hitl_lower_threshold(self) -> float:
        return self._hitl_lower

    def alias_count(self) -> int:
        return len(self._aliases)
