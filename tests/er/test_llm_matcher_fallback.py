"""WP4.3 / ADR-022 — LLM-matcher fallback for the borderline (needs_review) band.

Auto-accept high (untouched) / reject low (already dropped) / **LLM the middle**:
the LLM accepts (clear needs_review), rejects (drop), or is undecided (keep for HITL).
"""

from __future__ import annotations

from typing import Any

from src.er.canonical_index import ResolvedMention
from src.er.llm_matcher import GatewayLLMMatcher
from src.extraction.pass1_mention_extractor import Pass1MentionExtractor
from src.gateway.api import MockProvider, ModelGateway, TaskID


class _FakeIndex:
    def __init__(self, aliases: dict[str, str]) -> None:
        self._a = aliases

    def aliases(self) -> dict[str, str]:
        return dict(self._a)

    def canonical_name(self, canonical_id: str) -> str | None:
        for alias, cid in self._a.items():
            if cid == canonical_id:
                return alias
        return None

    def resolve(
        self, alias_text: str, *, context: str = "", default_type: str = "school",
    ) -> ResolvedMention | None:
        _ = context, default_type
        cid = self._a.get(alias_text)
        if cid is None:
            return None
        return ResolvedMention(
            canonical_id=cid, canonical_name=self.canonical_name(cid) or alias_text,
            confidence=1.0, reason="unique", needs_review=False,
        )


class _StubMatcher:
    def __init__(self, verdict: bool | None) -> None:
        self.verdict = verdict

    def resolve(self, text: str, canonical_name: str) -> bool | None:
        _ = text, canonical_name
        return self.verdict


_BORDERLINE_TEXT = "applying to university of pennsylvana this cycle"


def _extractor(matcher: Any = None) -> Pass1MentionExtractor:
    idx = _FakeIndex({"University of Pennsylvania": "school:upenn"})
    return Pass1MentionExtractor(
        idx,  # type: ignore[arg-type]
        auto_accept_threshold=99.0, hitl_lower_threshold=70.0,
        llm_matcher=matcher,
    )


def test_setup_yields_a_borderline_mention() -> None:
    (m,) = _extractor().extract(_BORDERLINE_TEXT)
    assert m.canonical_id == "school:upenn"
    assert m.needs_review is True  # in the 70-99 band → fallback territory


def test_llm_accepts_borderline() -> None:
    (m,) = _extractor(_StubMatcher(True)).extract(_BORDERLINE_TEXT)
    assert m.needs_review is False  # promoted to auto-accept by the LLM


def test_llm_rejects_borderline() -> None:
    assert _extractor(_StubMatcher(False)).extract(_BORDERLINE_TEXT) == []  # dropped


def test_llm_undecided_keeps_for_hitl() -> None:
    (m,) = _extractor(_StubMatcher(None)).extract(_BORDERLINE_TEXT)
    assert m.needs_review is True  # undecided → still HITL


def test_gateway_matcher_resolves_via_mock() -> None:
    gw = ModelGateway()
    gw.register(
        TaskID.ENTITY_MATCH_HARD,
        MockProvider(vendor="gemini", fixture=lambda _p: '{"is_match": true, "reasoning": "ok"}'),
    )
    assert GatewayLLMMatcher(gw).resolve("text about Penn", "University of Pennsylvania") is True


def test_gateway_matcher_undecided_when_unconfigured() -> None:
    # No client for the task → gateway raises → matcher returns None (keep for HITL).
    assert GatewayLLMMatcher(ModelGateway()).resolve("x", "Y") is None
