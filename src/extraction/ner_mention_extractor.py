"""NER-first mention extraction (ADR-022, WP4.2 — NuNER-Zero adopted).

The rapidfuzz substring matcher (`Pass1MentionExtractor`) has high recall but
low precision on real forum text — it fires on common-word substrings and
over-matches long names (bake-off precision 0.64; see
`.agent/reports/v1.7-wp4.2-ner-bakeoff.md`). A zero-shot NER model first detects
*entity spans*, and each span is then resolved against the canonical index — so
matching happens on a tight candidate span, not the whole post. The bake-off
picked **NuNER-Zero** (P/R/F1 ≈ 0.99/1.00/1.00, type-acc 0.91) over GLiNER-v2.1.

`gliner` is an **optional** dependency (heavy: torch + a ~0.5 GB model), imported
lazily so the package still imports without it. The model can be injected for
tests. Output `Mention`s are the same type the rapidfuzz path emits, so this is a
drop-in alternative behind the same shape.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from rapidfuzz import fuzz

from src.extraction.pass1_mention_extractor import Mention

if TYPE_CHECKING:
    from src.er.canonical_index import CanonicalIndex

# Zero-shot labels the model is asked to tag. Coarse on purpose — resolution to a
# canonical id is the canonical index's job, not the NER's.
ENTITY_LABELS: tuple[str, ...] = (
    "dental school", "dental specialty", "residency program", "university",
)
DEFAULT_MODEL_ID = "numind/NuNER_Zero"


class _NERModel(Protocol):
    def predict_entities(
        self, text: str, labels: list[str], threshold: float,
    ) -> list[dict[str, Any]]: ...


class NERMentionExtractor:
    """Detect entity spans with NuNER-Zero, resolve each against the canonical index."""

    def __init__(
        self,
        index: CanonicalIndex,
        *,
        model: _NERModel | None = None,
        model_id: str = DEFAULT_MODEL_ID,
        ner_threshold: float = 0.4,
        resolve_accept: float = 90.0,
        resolve_hitl_lower: float = 75.0,
    ) -> None:
        self._index = index
        self._model = model
        self._model_id = model_id
        self._ner_threshold = ner_threshold
        self._accept = resolve_accept
        self._hitl_lower = resolve_hitl_lower
        aliases = index.aliases()
        self._aliases: list[str] = list(aliases)
        self._alias_to_canonical: dict[str, str] = dict(aliases)

    def _ensure_model(self) -> _NERModel:
        if self._model is None:
            from gliner import GLiNER  # noqa: PLC0415 — optional heavy dep, lazy

            self._model = GLiNER.from_pretrained(self._model_id)
        return self._model

    def _resolve_span(self, span: str) -> Mention | None:
        """Resolve a detected span to a canonical entity via the alias universe.

        token_set_ratio against clean alias strings (the span is already a tight
        entity candidate, so this is far more precise than scanning a whole post).
        """
        best_alias, best_score = None, 0.0
        span_l = span.strip().lower()
        if not span_l:
            return None
        for alias in self._aliases:
            score = float(fuzz.token_set_ratio(span_l, alias.lower()))
            if score > best_score:
                best_alias, best_score = alias, score
        if best_alias is None or best_score < self._hitl_lower:
            return None
        canonical_id = self._alias_to_canonical[best_alias]
        return Mention(
            canonical_id=canonical_id,
            canonical_name=self._index.canonical_name(canonical_id) or best_alias,
            matched_alias=best_alias,
            score=best_score,
            needs_review=best_score < self._accept,
        )

    def extract(self, text: str) -> list[Mention]:
        """Return canonical mentions: NER spans resolved to the canonical index."""
        if not text:
            return []
        model = self._ensure_model()
        spans = model.predict_entities(text, list(ENTITY_LABELS), self._ner_threshold)
        best_by_canonical: dict[str, Mention] = {}
        for span in spans:
            mention = self._resolve_span(str(span.get("text", "")))
            if mention is None:
                continue
            prior = best_by_canonical.get(mention.canonical_id)
            if prior is None or mention.score > prior.score:
                best_by_canonical[mention.canonical_id] = mention
        return list(best_by_canonical.values())
