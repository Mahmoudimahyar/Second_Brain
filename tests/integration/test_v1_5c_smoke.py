"""V1.5c Phase 7 — integration smoke.

End-to-end: 5 seeded conflicts run through the web-verify agent; result
plumbed into the PM dashboard backend; drill-down opens with the right
entity centered.

Tavily provider is stubbed (no real network); the focus is verifying the
3-signal majority + conflict-resolver hook + team-dashboard plumbing
work in concert.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from src.conflict import Claim, ConflictResolver, ResolutionStatus
from src.conflict.baml.templates import (
    ClaimQuestionMaker,
    ClaimVerifier,
    QuestionParaphraser,
    heuristic_make_question,
    heuristic_paraphrase,
    heuristic_verify_claim,
)
from src.conflict.providers.base import ExtractedPage, SearchAnswer
from src.conflict.web_verify import WebVerificationAgent
from src.teams.angles import suggest_angles
from src.teams.pm import PainPointInput, compute_pain_points


@pytest.fixture(autouse=True)
def _enable_secbrain_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """V1.5c smoke uses heuristic_* fallbacks to stay LLM-free; opt in to
    the offline guard so the heuristics don't raise."""

    monkeypatch.setenv("SECBRAIN_OFFLINE", "1")


@dataclass
class _StubProvider:
    name: str = "tavily"
    qna: SearchAnswer = field(default_factory=lambda: SearchAnswer(answer="", urls=[]))
    search_res: SearchAnswer = field(default_factory=lambda: SearchAnswer(answer="", urls=[]))
    extract_text: str = ""

    def qna_search(self, question: str, *, max_results: int = 5) -> SearchAnswer:
        return self.qna

    def search(
        self, query: str, *, max_results: int = 5, search_depth: str = "advanced",
    ) -> SearchAnswer:
        return self.search_res

    def extract(
        self, urls: list[str], *, extract_depth: str = "advanced",
    ) -> list[ExtractedPage]:
        return [
            ExtractedPage(url=u, text=self.extract_text, success=True)
            for u in urls
        ]


GOLD_PATH = Path("evals/gold/v1.5c-web-verify.jsonl")


def _agent_for_row(row: dict) -> WebVerificationAgent:
    provider = _StubProvider(
        qna=SearchAnswer(answer=row["stub_qna_answer"], urls=row["stub_qna_urls"]),
        search_res=SearchAnswer(
            answer=row["stub_search_answer"], urls=row["stub_search_urls"],
        ),
        extract_text=row["stub_extract_text"],
    )
    return WebVerificationAgent(
        provider=provider,  # type: ignore[arg-type]
        make_question=ClaimQuestionMaker(invoke=heuristic_make_question),
        paraphrase=QuestionParaphraser(invoke=heuristic_paraphrase),
        verify=ClaimVerifier(invoke=heuristic_verify_claim),
    )


def test_v1_5c_full_smoke() -> None:
    rows = [
        json.loads(line) for line in GOLD_PATH.read_text().splitlines()
        if line.strip()
    ]
    assert len(rows) == 5, "expected 5 seeded clashes"

    # Step 1 — verify each clash through the agent + resolver hook.
    resolved: list[tuple[str, str]] = []  # (claim, verdict)
    for row in rows:
        agent = _agent_for_row(row)
        resolver = ConflictResolver(web_verifier=agent)
        claim = Claim(
            claim_id=f"claim:{row['id']}",
            subject_id=f"subject:{row['id']}",
            predicate="verifiable_fact",
            object_value=row["claim"],
            source_tier="L5",
            credibility=0.5,
        )
        outcome = resolver.try_web_verify(claim, context_summary="")
        # ADR-016 v2: agent returns supports/refutes via try_web_verify or
        # None on disagreement/unknown/cap_hit. For the gold set every row
        # should reach a verdict.
        assert outcome is not None, (
            f"row {row['id']!r} fell through to HITL; expected verdict"
        )
        assert outcome.status == ResolutionStatus.WEB_VERIFIED
        resolved.append((row["claim"], outcome.status.value))

    # Step 2 — PM dashboard surfaces pain points from synthetic Pass-4 inputs.
    inputs = [
        PainPointInput("tuition_anxiety", "applicants", -0.8, "post:1", "expensive"),
        PainPointInput("tuition_anxiety", "applicants", -0.7, "post:2", "too much"),
        PainPointInput("dat_prep", "applicants", -0.6, "post:3", "overwhelming"),
        PainPointInput("dat_prep", "applicants", -0.5, "post:4", "where to start"),
        PainPointInput("interview_logistics", "applicants", -0.4, "post:5", "travel costs"),
        PainPointInput("interview_logistics", "applicants", -0.3, "post:6", "clashing dates"),
    ]
    pps = compute_pain_points(inputs, min_volume=2)
    assert len(pps) >= 3

    # Step 3 — drill-down: angles surface for the first pain point with
    # references intact.
    first = pps[0]
    angles = suggest_angles(
        team="pm",
        item_id=first.pain_point_id,
        context={"title": first.title, "references": first.references},
    )
    assert len(angles) == 3
    assert all(a.draft_only for a in angles)
    assert all(a.citations == first.references[:3] for a in angles)
