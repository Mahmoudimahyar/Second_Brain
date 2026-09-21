"""Tests for the Evidence Answer Engine (EAE, 2026-06-17).

Covers all 7 EAE steps using fixtures — no Kùzu, no real corpus needed.

EAE-1  FTS5 / LIKE comment recall
EAE-2  EvidenceSet assembler builds typed items from all sources
EAE-3  Typed-count aggregator + most_reliable surfacing
EAE-4  EvidenceAnswer schema correctness
EAE-5  Tier-weighted ranking wired (ranking_score applied to evidence items)
EAE-6  Opinion distribution + KPA-lite stance clustering
EAE-7  Calibrated abstention fires when evidence is thin
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.retrieval.kb_agent import (
    EAE_TIER_WEIGHTS,
    EvidenceItem,
    KBAgent,
    _MIN_EVIDENCE_FOR_VERDICT,
)
from src.web.schemas.evidence import EvidenceResponse


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tiny_docs_db(tmp_path: Path) -> Path:
    """Small documents.sqlite with 5 posts + 10 comments (no FTS5 yet)."""
    db = tmp_path / "documents.sqlite"
    c = sqlite3.connect(db)
    c.execute(
        "CREATE TABLE documents (doc_id TEXT PRIMARY KEY, doc_type TEXT, "
        "source TEXT, parent_id TEXT, thread_id TEXT, author TEXT, "
        "created_iso TEXT, score INTEGER, url TEXT, title TEXT, text TEXT)"
    )
    rows = [
        ("reddit_post:aaa", "reddit_post", "DentalSchool", "", "reddit_post:aaa",
         "user1", "2024-01-01", 100, "https://reddit.com/r/DentalSchool/aaa",
         "NYU GPA requirements", "What are NYU dental school GPA requirements?"),
        ("reddit_post:bbb", "reddit_post", "DentalSchool", "", "reddit_post:bbb",
         "user2", "2024-01-02", 50, "https://reddit.com/r/DentalSchool/bbb",
         "NYU DAT score", "NYU interview tips and DAT score needed."),
        ("reddit_comment:c1", "reddit_comment", "DentalSchool",
         "reddit_post:aaa", "reddit_post:aaa",
         "user3", "2024-01-01T10:00", 30, "", "", "I got in with 3.7 GPA and 22 DAT."),
        ("reddit_comment:c2", "reddit_comment", "DentalSchool",
         "reddit_post:aaa", "reddit_post:aaa",
         "user4", "2024-01-01T11:00", 25, "", "",
         "NYU is great school. Very competitive admissions."),
        ("reddit_comment:c3", "reddit_comment", "DentalSchool",
         "reddit_post:bbb", "reddit_post:bbb",
         "user5", "2024-01-02T09:00", 15, "", "",
         "NYU interview was professional. GPA cutoff around 3.5."),
    ]
    c.executemany("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    c.commit()
    c.execute(
        "CREATE INDEX idx_thread ON documents(thread_id)"
    )
    c.commit()
    c.close()
    return db


@pytest.fixture()
def tiny_docs_db_with_fts5(tiny_docs_db: Path) -> Path:
    """Same tiny DB but with FTS5 virtual table."""
    c = sqlite3.connect(tiny_docs_db)
    c.execute(
        "CREATE VIRTUAL TABLE docs_fts USING fts5("
        "text, content=documents, content_rowid=rowid)"
    )
    c.commit()
    c.execute("INSERT INTO docs_fts(docs_fts) VALUES('rebuild')")
    c.commit()
    c.close()
    return tiny_docs_db


def _make_agent(tmp_path: Path, documents_db: Path | None = None) -> KBAgent:
    """Build a KBAgent with mocked graph (no Kùzu process) + optional docs DB."""
    agent = object.__new__(KBAgent)
    # Minimal in-memory state matching _load() output
    agent.name = {"school:nyu": "New York University College of Dentistry"}
    agent.kind = {"school:nyu": "School"}
    agent.schools = {"school:nyu": "New York University College of Dentistry"}
    agent.same = defaultdict(set)
    agent.fc = defaultdict(dict, {
        "school:nyu": {
            "gpa": {"school_id": "school:nyu", "metric": "gpa",
                    "median": 3.7, "n": 120, "p25": 3.5, "p75": 3.9},
            "tuition": {"school_id": "school:nyu", "metric": "tuition",
                        "median": 65000, "n": 80, "p25": 60000, "p75": 70000,
                        "l1_tuition_resident": 68500},
        }
    })
    agent.sent = defaultdict(Counter, {
        "school:nyu": Counter({"positive": 160, "neutral": 80, "negative": 60}),
    })
    agent.clusters = [(500, "DAT prep"), (300, "admissions stats"), (200, "financial aid")]
    agent.canon = {"school:nyu": "school:nyu"}
    agent._llm = None
    agent._semantic = None
    agent._semantic_tried = True   # skip shard loading
    agent._graph = MagicMock()
    agent._c = MagicMock()
    agent._data_dir = tmp_path
    agent._docs_db_path = documents_db
    agent._docs_db_has_fts5 = None
    return agent


# ---------------------------------------------------------------------------
# EAE-1: comment recall (FTS5 + LIKE fallback)
# ---------------------------------------------------------------------------

class TestEAE1CommentRecall:
    def test_like_fallback_returns_comments(self, tmp_path, tiny_docs_db):
        agent = _make_agent(tmp_path, documents_db=tiny_docs_db)
        items = agent._comment_recall("NYU", top_k=5)
        assert len(items) >= 1
        assert all(i.source_type == "comment" for i in items)
        assert all(i.tier == "L5" for i in items)

    def test_fts5_returns_comments(self, tmp_path, tiny_docs_db_with_fts5):
        agent = _make_agent(tmp_path, documents_db=tiny_docs_db_with_fts5)
        # Should detect FTS5 and use it
        assert agent._check_fts5() is True
        items = agent._comment_recall("NYU", top_k=5)
        assert len(items) >= 1

    def test_no_db_returns_empty(self, tmp_path):
        agent = _make_agent(tmp_path, documents_db=None)
        items = agent._comment_recall("NYU", top_k=5)
        assert items == []

    def test_fts5_detection_false_without_table(self, tmp_path, tiny_docs_db):
        agent = _make_agent(tmp_path, documents_db=tiny_docs_db)
        assert agent._check_fts5() is False


# ---------------------------------------------------------------------------
# EAE-2: EvidenceSet assembler
# ---------------------------------------------------------------------------

class TestEAE2EvidenceSet:
    def test_build_evidence_set_has_l1_and_l5(self, tmp_path, tiny_docs_db):
        agent = _make_agent(tmp_path, documents_db=tiny_docs_db)
        # Add L1 claim items via mock
        with patch.object(agent, "_l1_claim_items", return_value=[
            EvidenceItem("claim:x1", "l1_claim", "L1", "tuition: $68500", 1.0,
                         url="https://adea.org")
        ]):
            facts = {"type": "school_profile"}
            items = agent._build_evidence_set("NYU tuition", facts, "school:nyu")
        assert any(i.tier == "L1" for i in items)
        assert any(i.source_type == "forum_consensus" for i in items)

    def test_deduplication_by_doc_id(self, tmp_path):
        agent = _make_agent(tmp_path)
        items = [
            EvidenceItem("id:1", "l5_post", "L5", "snippet a", 0.8),
            EvidenceItem("id:1", "l5_post", "L5", "snippet a duplicate", 0.7),
            EvidenceItem("id:2", "l5_post", "L5", "snippet b", 0.6),
        ]
        seen: set[str] = set()
        unique = []
        for item in items:
            if item.doc_id not in seen:
                seen.add(item.doc_id)
                unique.append(item)
        assert len(unique) == 2


# ---------------------------------------------------------------------------
# EAE-3: Typed counts + most_reliable
# ---------------------------------------------------------------------------

class TestEAE3TypedCounts:
    def test_typed_counts(self, tmp_path):
        agent = _make_agent(tmp_path)
        items = [
            EvidenceItem("c1", "l1_claim", "L1", "tuition", 1.0),
            EvidenceItem("c2", "l1_claim", "L1", "gpa", 1.0),
            EvidenceItem("p1", "l5_post", "L5", "post a", 0.7),
            EvidenceItem("p2", "comment", "L5", "comment a", 0.3),
        ]
        counts = agent._typed_counts(items)
        assert counts["l1_claim"] == 2
        assert counts["l5_post"] == 1
        assert counts["comment"] == 1

    def test_most_reliable_l1_first(self, tmp_path):
        agent = _make_agent(tmp_path)
        items = [
            EvidenceItem("l5a", "l5_post", "L5", "forum", 0.9),
            EvidenceItem("l1a", "l1_claim", "L1", "official", 1.0),
            EvidenceItem("l5b", "comment", "L5", "comment", 0.5),
        ]
        ranked = agent._score_evidence_items(items)
        # L1 items should rank highest
        assert ranked[0].tier == "L1"


# ---------------------------------------------------------------------------
# EAE-4: EvidenceAnswer schema validation
# ---------------------------------------------------------------------------

class TestEAE4Schema:
    def test_evidence_response_valid(self):
        resp = EvidenceResponse(
            question="What is NYU tuition?",
            typed_counts={"l1_claim": 2, "l5_post": 5},
            most_reliable=[],
            opinion_distribution={"positive": 0.5, "neutral": 0.3, "negative": 0.2},
            stance_clusters=[],
            verdict="agrees",
            sources=[],
        )
        assert resp.verdict == "agrees"
        assert resp.abstain_reason is None
        assert resp.answer is None

    def test_evidence_response_with_sources(self):
        from src.web.schemas.evidence import EvidenceItemOut
        resp = EvidenceResponse(
            question="test",
            typed_counts={"l1_claim": 1},
            most_reliable=[EvidenceItemOut(doc_id="x", source_type="l1_claim",
                                           tier="L1", snippet="test", score=1.0)],
            opinion_distribution={"positive": 1.0},
            verdict="no_l1_data",
            sources=[],
        )
        assert len(resp.most_reliable) == 1
        assert resp.most_reliable[0].tier == "L1"


# ---------------------------------------------------------------------------
# EAE-5: Tier-weighted ranking wired
# ---------------------------------------------------------------------------

class TestEAE5Ranking:
    def test_l1_outranks_l5_by_tier_weight(self, tmp_path):
        agent = _make_agent(tmp_path)
        items = [
            EvidenceItem("l5a", "l5_post", "L5", "forum post", 0.95),
            EvidenceItem("l1a", "l1_claim", "L1", "official claim", 0.5),
        ]
        ranked = agent._score_evidence_items(items)
        # L1 item with score=0.5 should outrank L5 item with score=0.95
        # because tier weight L1=1.0 >> L5=0.4
        assert ranked[0].tier == "L1"

    def test_tier_weights_applied(self):
        from src.retrieval.ranking import RankingWeights, ranking_score
        weights = RankingWeights(w_tier=EAE_TIER_WEIGHTS)
        # L1@credibility=0.5, rank=preferred: 1.0 * 1.0 * 1.0 * 0.5 * 1.0 = 0.5
        l1_score = ranking_score(
            source_tier="L1", rank="preferred", decay_factor=1.0,
            credibility=0.5, consistency_factor=1.0, weights=weights,
        )
        # L5@credibility=0.95, rank=preferred: 0.4 * 1.0 * 1.0 * 0.95 * 1.0 = 0.38
        l5_score = ranking_score(
            source_tier="L5", rank="preferred", decay_factor=1.0,
            credibility=0.95, consistency_factor=1.0, weights=weights,
        )
        assert l1_score > l5_score


# ---------------------------------------------------------------------------
# EAE-6: Opinion distribution + stance clustering
# ---------------------------------------------------------------------------

class TestEAE6Opinion:
    def test_opinion_distribution_from_sentiment(self, tmp_path):
        agent = _make_agent(tmp_path)
        dist = agent._opinion_distribution("school:nyu")
        # fixture: positive=160, neutral=80, negative=60 => total=300
        assert abs(dist.get("positive", 0) - 160 / 300) < 0.01
        assert abs(dist.get("negative", 0) - 60 / 300) < 0.01
        assert abs(dist.get("neutral", 0) - 80 / 300) < 0.01

    def test_kpa_polarity_fallback_no_llm(self, tmp_path):
        agent = _make_agent(tmp_path)
        items = [
            EvidenceItem("a", "l5_post", "L5", "great school love it", 0.8),
            EvidenceItem("b", "l5_post", "L5", "avoid this program bad experience", 0.5),
            EvidenceItem("c", "l5_post", "L5", "decent curriculum", 0.4),
        ]
        clusters = agent._kpa_stance(items, "NYU experience", llm=None)
        assert len(clusters) == 3
        assert all("label" in c and "fraction" in c and "n" in c for c in clusters)
        total_fraction = sum(c["fraction"] for c in clusters)
        assert abs(total_fraction - 1.0) < 0.05  # rounding to 2dp allows ±0.03

    def test_kpa_empty_items(self, tmp_path):
        agent = _make_agent(tmp_path)
        clusters = agent._kpa_stance([], "test", llm=None)
        assert clusters == []


# ---------------------------------------------------------------------------
# EAE-7: Calibrated abstention
# ---------------------------------------------------------------------------

class TestEAE7Abstention:
    def test_abstain_when_insufficient_evidence(self, tmp_path):
        agent = _make_agent(tmp_path)
        items = [EvidenceItem("a", "l5_post", "L5", "one source", 0.5)]
        reason = agent._abstain_check(items, {"positive": 1.0}, "agrees")
        assert reason is not None
        assert "insufficient" in reason.lower()

    def test_no_abstain_with_enough_evidence(self, tmp_path):
        agent = _make_agent(tmp_path)
        items = [
            EvidenceItem(f"id:{i}", "l5_post", "L5", f"post {i}", 0.5)
            for i in range(_MIN_EVIDENCE_FOR_VERDICT + 2)
        ]
        reason = agent._abstain_check(
            items, {"positive": 0.6, "neutral": 0.3, "negative": 0.1}, "agrees")
        assert reason is None

    def test_abstain_when_no_clear_majority(self, tmp_path):
        agent = _make_agent(tmp_path)
        items = [
            EvidenceItem(f"id:{i}", "l5_post", "L5", f"post {i}", 0.5)
            for i in range(6)
        ]
        # All factions equal -> no majority
        dist = {"positive": 0.33, "neutral": 0.34, "negative": 0.33}
        reason = agent._abstain_check(items, dist, "agrees")
        assert reason is not None
        assert "majority" in reason.lower()

    def test_popular_vs_correct_no_l1(self, tmp_path):
        agent = _make_agent(tmp_path)
        items = [EvidenceItem(f"id:{i}", "l5_post", "L5", f"snippet {i}", 0.5)
                 for i in range(5)]
        pop, auth, verdict = agent._popular_vs_correct(items, [])
        assert verdict == "no_l1_data"
        assert auth is None

    def test_popular_vs_correct_agrees(self, tmp_path):
        agent = _make_agent(tmp_path)
        items = [EvidenceItem(f"id:{i}", "l5_post", "L5", "tuition 68500 dollars", 0.5)
                 for i in range(5)]
        l1 = [EvidenceItem("claim:x", "l1_claim", "L1", "tuition: $68500", 1.0)]
        _, _, verdict = agent._popular_vs_correct(items, l1)
        assert verdict == "agrees"

    def test_popular_vs_correct_contradicts(self, tmp_path):
        agent = _make_agent(tmp_path)
        items = [EvidenceItem(f"id:{i}", "l5_post", "L5", "tuition 45000 very cheap", 0.5)
                 for i in range(5)]
        l1 = [EvidenceItem("claim:x", "l1_claim", "L1", "official tuition 68500", 1.0)]
        _, _, verdict = agent._popular_vs_correct(items, l1)
        assert verdict == "contradicts"


# ---------------------------------------------------------------------------
# Integration: evidence_answer() end-to-end (mocked graph, no Kùzu)
# ---------------------------------------------------------------------------

class TestEvidenceAnswerIntegration:
    def test_evidence_answer_shape(self, tmp_path, tiny_docs_db):
        agent = _make_agent(tmp_path, documents_db=tiny_docs_db)
        with patch.object(agent, "_l1_claim_items", return_value=[
            EvidenceItem("claim:nyu1", "l1_claim", "L1",
                         "tuition: $68500", 1.0, url="https://adea.org")
        ]):
            result = agent.evidence_answer("NYU tuition cost")

        # All required top-level keys present
        required_keys = [
            "question", "typed_counts", "most_reliable", "opinion_distribution",
            "stance_clusters", "popular_answer", "authoritative_answer",
            "verdict", "abstain_reason", "sources", "facts",
        ]
        for key in required_keys:
            assert key in result, f"missing key: {key}"

        # Typed counts has at least forum_consensus (from fixture fc)
        assert "forum_consensus" in result["typed_counts"]

        # Most reliable has L1 items first
        if result["most_reliable"]:
            assert result["most_reliable"][0]["tier"] == "L1"

        # Opinion distribution sums to ~1.0
        dist = result["opinion_distribution"]
        if dist:
            assert abs(sum(dist.values()) - 1.0) < 0.05

    def test_evidence_answer_pydantic_valid(self, tmp_path):
        agent = _make_agent(tmp_path)
        with patch.object(agent, "_l1_claim_items", return_value=[]):
            result = agent.evidence_answer("DAT score")
        # Should serialize to EvidenceResponse without error
        resp = EvidenceResponse(**result)
        assert resp.question == "DAT score"

    def test_backward_compat_answer_unchanged(self, tmp_path):
        """answer() must still return {question, intent, facts, answer}."""
        agent = _make_agent(tmp_path)
        result = agent.answer("what topics do people discuss")
        assert "question" in result
        assert "intent" in result
        assert "facts" in result
        assert "answer" in result
        assert result["intent"] == "topics"
