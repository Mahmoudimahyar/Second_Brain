"""V1 entity resolution. Pass 1 = deterministic fuzzy match; Pass 2+ adds HNSW + reranker."""

from src.er.canonical_index import CanonicalIndex
from src.er.fuzzy_match import FuzzyMatch, FuzzySchoolMatcher

__all__ = ["CanonicalIndex", "FuzzyMatch", "FuzzySchoolMatcher"]
