from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz, process

from src.er.canonical_index import CanonicalIndex


@dataclass(frozen=True)
class FuzzyMatch:
    mention: str
    canonical_id: str
    canonical_name: str
    score: float  # rapidfuzz token_set_ratio in [0, 100]
    matched_alias: str


class FuzzySchoolMatcher:
    """Pass 1 deterministic canonical-name matcher per `plan.md` Pass 1.

    Uses `rapidfuzz.fuzz.token_set_ratio` against the L1 canonical alias
    universe. The default threshold of 95 implements the conservative
    auto-accept criterion (FR-3.1 raised the bar to ≥ 0.90 cosine on the
    DITTO reranker; this is the simpler text-only V1 Pass 1 pre-filter and
    runs at $0 with deterministic output).
    """

    DEFAULT_THRESHOLD: float = 95.0

    def __init__(
        self,
        index: CanonicalIndex,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        if not 0 <= threshold <= 100:
            raise ValueError(f"threshold must be in [0, 100], got {threshold}")
        self._index = index
        self._threshold = float(threshold)
        aliases = index.aliases()
        self._aliases: list[str] = list(aliases.keys())
        self._aliases_lower: list[str] = [a.lower() for a in self._aliases]
        self._alias_to_canonical: dict[str, str] = dict(aliases)

    def match(self, mention: str) -> FuzzyMatch | None:
        if not mention or not mention.strip() or not self._aliases:
            return None
        query = mention.strip().lower()
        choice = process.extractOne(
            query,
            self._aliases_lower,
            scorer=fuzz.token_set_ratio,
            score_cutoff=self._threshold,
        )
        if choice is None:
            return None
        _matched_lower, score, idx = choice
        original_alias = self._aliases[idx]
        canonical_id = self._alias_to_canonical[original_alias]
        canonical_name = (
            self._index.canonical_name(canonical_id) or original_alias
        )
        return FuzzyMatch(
            mention=mention,
            canonical_id=canonical_id,
            canonical_name=canonical_name,
            matched_alias=original_alias,
            score=float(score),
        )

    def match_many(self, mentions: list[str]) -> list[FuzzyMatch | None]:
        return [self.match(m) for m in mentions]

    @property
    def threshold(self) -> float:
        return self._threshold

    def alias_count(self) -> int:
        return len(self._aliases)
