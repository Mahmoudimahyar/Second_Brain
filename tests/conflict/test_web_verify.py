"""Tests for V1.5c Phase 2 — `WebVerificationAgent` (ADR-016 v2)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.conflict.baml.templates import (
    ClaimQuestionMaker,
    ClaimVerifier,
    QuestionParaphraser,
    VerifyResult,
    heuristic_make_question,
    heuristic_paraphrase,
)
from src.conflict.providers.base import ExtractedPage, SearchAnswer
from src.conflict.web_verify import (
    CostBudget,
    WebVerificationAgent,
    WebVerificationCache,
)


@dataclass
class _StubProvider:
    """SearchProvider stub seeded with canned responses."""

    name: str = "tavily"
    qna_answer: str = ""
    qna_urls: list[str] = field(default_factory=list)
    search_answer: str = ""
    search_urls: list[str] = field(default_factory=list)
    extract_text: str = ""

    def qna_search(self, question: str, *, max_results: int = 5) -> SearchAnswer:
        return SearchAnswer(
            answer=self.qna_answer,
            urls=list(self.qna_urls),
            raw_response={"question": question},
            provider="tavily",
        )

    def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        search_depth: str = "advanced",
    ) -> SearchAnswer:
        return SearchAnswer(
            answer=self.search_answer,
            urls=list(self.search_urls),
            raw_response={"query": query},
            provider="tavily",
        )

    def extract(
        self,
        urls: list[str],
        *,
        extract_depth: str = "advanced",
    ) -> list[ExtractedPage]:
        return [
            ExtractedPage(
                url=u, title="", text=self.extract_text, raw_html="",
                success=True,
            )
            for u in urls
        ]


def _agent(provider: _StubProvider, **overrides: Any) -> WebVerificationAgent:
    return WebVerificationAgent(
        provider=provider,  # type: ignore[arg-type]
        make_question=ClaimQuestionMaker(invoke=heuristic_make_question),
        paraphrase=QuestionParaphraser(invoke=heuristic_paraphrase),
        verify=ClaimVerifier(invoke=_verifier_from_overlap),
        **overrides,
    )


def _verifier_from_overlap(claim: str, evidence: str) -> VerifyResult:
    """Test verifier — lexical overlap above 0.3 → supports."""

    c_tokens = set(claim.lower().split())
    e_tokens = set(evidence.lower().split())
    overlap = len(c_tokens & e_tokens) / max(len(c_tokens), 1)
    if overlap < 0.30:
        return VerifyResult(verdict="unknown", evidence_excerpt=evidence[:200], confidence=overlap)
    return VerifyResult(
        verdict="supports", evidence_excerpt=evidence[:200],
        confidence=min(overlap, 0.95),
    )


def test_three_signals_majority_writes_verdict() -> None:
    provider = _StubProvider(
        qna_answer="NYU dental tuition for 2024-25 was approximately $87,000 per year.",
        qna_urls=["https://dental.nyu.edu/tuition"],
        search_answer="NYU dental school tuition is about $87,000 annually for the 2024-25 cycle.",
        search_urls=["https://example.org/nyu-tuition"],
        extract_text="New York University College of Dentistry tuition $87,000 for 2024-25.",
    )
    agent = _agent(provider)
    result = agent.verify_claim(
        "NYU dental school tuition for 2024-25 was approximately $87,000",
    )
    assert result.verdict == "supports"
    assert result.confidence >= 0.5
    assert len(result.citations) > 0


def test_refutes_when_signals_say_no() -> None:
    provider = _StubProvider(
        qna_answer="No, UCLA School of Dentistry is in Los Angeles, not San Francisco.",
        qna_urls=["https://dentistry.ucla.edu"],
        search_answer="Incorrect: UCLA dental school is in Los Angeles, not San Francisco.",
        search_urls=["https://example.org/ucla"],
        extract_text="UCLA School of Dentistry Los Angeles campus.",
    )
    agent = _agent(provider)
    result = agent.verify_claim("UCLA dental school is located in San Francisco")
    assert result.verdict == "refutes"


def test_cap_hit_returns_cap_hit() -> None:
    provider = _StubProvider()
    budget = CostBudget(cap_usd=1.0, spent_usd=1.5)
    agent = _agent(provider, cost_budget=budget)
    result = agent.verify_claim("anything")
    assert result.verdict == "cap_hit"


def test_cache_hit_returns_same_result() -> None:
    provider = _StubProvider(
        qna_answer="supports answer here", qna_urls=["https://x"],
        search_answer="also supports", search_urls=["https://y"],
        extract_text="some evidence text",
    )
    cache = WebVerificationCache()
    agent = _agent(provider, cache=cache)
    first = agent.verify_claim("a claim")
    second = agent.verify_claim("a claim")
    assert first.run.run_id == second.run.run_id
    # Cache entry should be present
    assert cache.get(cache.key("a claim", "")) is not None


def test_all_unknown_returns_unknown() -> None:
    provider = _StubProvider(qna_answer="", qna_urls=[], search_answer="", search_urls=[])
    result = _agent(provider).verify_claim("untestable claim")
    assert result.verdict == "unknown"


# ---------------------------------------------------------------------
# Gold set
# ---------------------------------------------------------------------


GOLD_PATH = Path("evals/gold/v1.5c-web-verify.jsonl")


def test_gold_set_size() -> None:
    rows = [
        json.loads(line) for line in GOLD_PATH.read_text().splitlines()
        if line.strip()
    ]
    assert len(rows) == 5


def test_gold_set_all_resolve_correctly() -> None:
    """AC-1: web-verify reaches the expected verdict on 5 seeded clashes."""

    rows = [
        json.loads(line) for line in GOLD_PATH.read_text().splitlines()
        if line.strip()
    ]
    correct = 0
    for row in rows:
        provider = _StubProvider(
            qna_answer=row["stub_qna_answer"],
            qna_urls=row["stub_qna_urls"],
            search_answer=row["stub_search_answer"],
            search_urls=row["stub_search_urls"],
            extract_text=row["stub_extract_text"],
        )
        agent = _agent(provider)
        result = agent.verify_claim(row["claim"])
        if result.verdict == row["expected_verdict"]:
            correct += 1
    assert correct == 5, (
        f"web-verify reached only {correct}/5 expected verdicts"
    )
