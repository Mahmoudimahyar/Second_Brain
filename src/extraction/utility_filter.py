from __future__ import annotations

import re
from dataclasses import dataclass

# Per `docs/04-architecture/system-overview.md` §5 + A-057.
# The utility filter avoids LLM tokens at Pass 4. The graph keeps every post
# (R5 standing rule); only the LLM-input selection is filtered.

_BOT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(re.compile(p) for p in (
    r"^AutoModerator$",
    r".*[Bb][Oo][Tt]_$",
    r".*-Bot$",
))
_MIN_BODY_LEN_REPLY: int = 20         # very-short reply threshold
_QUESTION_RE = re.compile(r"\?\s*$")
_SENTIMENT_MARKERS = frozenset({
    "good", "bad", "great", "awful", "love", "hate", "best", "worst",
    "recommend", "avoid", "amazing", "terrible",
})


@dataclass(frozen=True)
class FilterDecision:
    keep: bool
    reason: str       # rule that fired; "kept" when accepted
    mentions_entity: bool


@dataclass(frozen=True)
class FilterContext:
    """Input bundle for the utility filter."""

    text: str
    author: str | None
    is_reply: bool                    # True for comments, False for top-level posts
    is_crosspost: bool = False
    duplicate_of: str | None = None
    mentions_entity: bool = False     # populated by Pass 1 fuzzy match
    score: int | None = None          # Reddit score; None for SDN


def filter_post(ctx: FilterContext) -> FilterDecision:
    """Pass 4 utility filter (A-057).

    Drops:
      1. Posts with no author ([deleted] / [removed])
      2. Bot patterns (AutoModerator, *_bot_, *-Bot)
      3. Very-short replies (< 20 chars body) that don't mention an entity
      4. Crosspost duplicates
      5. "Generic" — no entity AND no question AND no sentiment marker

    `prescient_correct` preservation: even very-low-score posts that mention a
    known entity are kept (A-032).
    """

    text = (ctx.text or "").strip()

    if ctx.author is None:
        return FilterDecision(False, "no_author_deleted_or_removed",
                              mentions_entity=ctx.mentions_entity)

    if _is_bot(ctx.author):
        return FilterDecision(False, "bot_author", mentions_entity=ctx.mentions_entity)

    if ctx.is_crosspost and ctx.duplicate_of is not None:
        return FilterDecision(False, "crosspost_duplicate",
                              mentions_entity=ctx.mentions_entity)

    if (
        ctx.is_reply
        and len(text) < _MIN_BODY_LEN_REPLY
        and not ctx.mentions_entity
    ):
        return FilterDecision(False, "very_short_reply_no_entity",
                              mentions_entity=False)

    if (
        not ctx.mentions_entity
        and not _QUESTION_RE.search(text)
        and not _has_sentiment_marker(text)
    ):
        return FilterDecision(False, "generic_no_entity_no_question_no_sentiment",
                              mentions_entity=False)

    return FilterDecision(True, "kept", mentions_entity=ctx.mentions_entity)


def _is_bot(author: str) -> bool:
    return any(p.match(author) for p in _BOT_PATTERNS)


def _has_sentiment_marker(text: str) -> bool:
    lowered = text.lower()
    return any(m in lowered for m in _SENTIMENT_MARKERS)
