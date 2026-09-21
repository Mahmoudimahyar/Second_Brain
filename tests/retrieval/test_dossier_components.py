"""Unit tests for the Evidence Dossier components (ED-3 … ED-6) — pure logic, no
bundle artifacts. The end-to-end pipeline is validated on the VM against real data;
these lock the parsing/term/alias/verdict logic so regressions are caught in CI.
"""

from __future__ import annotations

from src.retrieval.adjudicator import VERDICTS, adjudicate
from src.retrieval.evidence_census import build_fts_query
from src.retrieval.evidence_recall import _topic_term_list, derive_aliases
from src.retrieval.l1_retrieval import L1ArticleIndex
from src.retrieval.stance import _parse_positions, derive_positions


class MockLLM:
    """Minimal gateway-shaped LLM: .complete(prompt, schema, temperature) -> .raw_text.
    Accepts **kwargs so the deterministic `temperature=0` calls don't break."""

    def __init__(self, text: str) -> None:
        self._t = text
        self.calls: list[dict] = []

    def complete(self, prompt: str, schema=None, **kwargs):  # noqa: ANN001, ARG002
        self.calls.append(kwargs)
        return type("R", (), {"raw_text": self._t})()


class SeqLLM:
    """Returns a queued sequence of raw_texts across successive complete() calls."""

    def __init__(self, texts: list[str]) -> None:
        self._texts = list(texts)
        self.n = 0

    def complete(self, prompt: str, schema=None, **kwargs):  # noqa: ANN001, ARG002
        t = self._texts[min(self.n, len(self._texts) - 1)]
        self.n += 1
        return type("R", (), {"raw_text": t})()


# --- FTS query construction (ED-2) -----------------------------------------

def test_build_fts_query_terms_and_or():
    q = build_fts_query("NYU tuition cost")
    assert '"tuition"' in q and '"cost"' in q
    assert " OR " in q


def test_build_fts_query_drops_stopwords_and_short():
    q = build_fts_query("how is the cost")
    assert "how" not in q and '"the"' not in q
    assert '"cost"' in q


def test_build_fts_query_empty_when_no_terms():
    assert build_fts_query("is it") == ""


# --- alias derivation + topic separation (ED-3) ----------------------------

def test_derive_aliases_nyu():
    al = derive_aliases("NEW YORK UNIVERSITY COLLEGE OF DENTISTRY")
    assert "nyu" in al
    assert "new york university" in al


def test_derive_aliases_ucsf_prefix_acronym():
    al = derive_aliases("University of California San Francisco School of Dentistry")
    assert "ucsf" in al


def test_topic_terms_strip_school_tokens():
    terms = _topic_term_list("NYU tuition cost and student loans",
                             ["nyu", "new york university"])
    assert "nyu" not in terms
    assert "tuition" in terms and "loans" in terms


def test_topic_terms_drop_generic_dental_words():
    # "dental"/"school" are generic in this corpus and must not gate the topic.
    terms = _topic_term_list("dental school interview experience", [])
    assert "dental" not in terms and "school" not in terms
    assert "interview" in terms


# --- adjudicator (ED-6) -----------------------------------------------------

_STANCE = {"positions": [{"label": "Too Expensive", "fraction": 0.70, "n": 7000,
                          "description": "overpriced"}]}


def test_adjudicate_no_l1_abstains():
    out = adjudicate(None, "NYU tuition", _STANCE, [], [])
    assert out["verdict"] == "no_official_source"
    assert out["authoritative_answer"] is None
    assert out["popular_answer"] == "Too Expensive"


def test_adjudicate_no_llm_but_l1_present_needs_research():
    out = adjudicate(None, "NYU tuition", _STANCE, [{"predicate": "tuition", "value": 1}], [])
    assert out["verdict"] == "needs_research"


def test_adjudicate_with_llm_parses_verdict():
    llm = MockLLM('{"verdict": "popular_confirmed", "authoritative_answer": "NYU is '
                  'among the most expensive.", "popular_answer": "Too Expensive", '
                  '"why": "Official cost data agrees."}')
    out = adjudicate(llm, "NYU tuition", _STANCE,
                     [{"predicate": "tuition_resident", "value": 80000}], [])
    assert out["verdict"] == "popular_confirmed"
    assert "expensive" in out["authoritative_answer"].lower()


def test_adjudicate_unknown_verdict_defaults_combination():
    llm = MockLLM('{"verdict": "nonsense", "authoritative_answer": "x", "why": "y"}')
    out = adjudicate(llm, "q", _STANCE, [{"predicate": "p", "value": "v"}], [])
    assert out["verdict"] == "combination"


def test_adjudicate_garbage_response_needs_research():
    out = adjudicate(MockLLM("not json at all"), "q", _STANCE,
                     [{"predicate": "p", "value": "v"}], [])
    assert out["verdict"] == "needs_research"


def test_verdict_vocabulary_is_closed():
    assert "popular_is_wrong" in VERDICTS and "needs_research" in VERDICTS


# --- stance position parsing (ED-5) ----------------------------------------

def test_derive_positions_parses_json_array():
    llm = MockLLM('Here: [{"label": "Worth it", "description": "good ROI"}, '
                  '{"label": "Avoid", "description": "too much debt"}]')
    pos = derive_positions(llm, "is NYU worth it", ["snippet a", "snippet b"])
    assert len(pos) == 2
    assert pos[0]["label"] == "Worth it"


def test_derive_positions_caps_at_max():
    arr = ",".join('{"label": "P%d", "description": "d"}' % i for i in range(8))
    pos = derive_positions(MockLLM(f"[{arr}]"), "q", ["s"], max_positions=4)
    assert len(pos) == 4


def test_derive_positions_bad_json_returns_empty():
    assert derive_positions(MockLLM("no json"), "q", ["s"]) == []


# --- regression: stance robustness (issue #1 — flaky/empty opinion distribution) ----

def test_parse_positions_handles_markdown_fences():
    raw = '```json\n[{"label": "A", "description": "x"}]\n```'
    pos = _parse_positions(raw, 4)
    assert len(pos) == 1 and pos[0]["label"] == "A"


def test_parse_positions_handles_trailing_prose():
    raw = 'Sure! [{"label": "A", "description": "x"}] Hope that helps.'
    assert len(_parse_positions(raw, 4)) == 1


def test_parse_positions_non_list_returns_empty():
    assert _parse_positions('{"label": "A"}', 4) == []
    assert _parse_positions("not json", 4) == []


def test_derive_positions_retries_on_empty_then_succeeds():
    # First call yields no parseable array; retry yields a valid one (the bug that
    # intermittently dropped the opinion distribution must self-heal).
    llm = SeqLLM(["sorry, no JSON here",
                  '[{"label": "Worth it", "description": "ROI"}]'])
    pos = derive_positions(llm, "q", ["s"], attempts=2)
    assert len(pos) == 1 and pos[0]["label"] == "Worth it"
    assert llm.n == 2  # it actually retried


def test_derive_positions_first_attempt_is_deterministic():
    llm = MockLLM('[{"label": "A", "description": "x"}]')
    derive_positions(llm, "q", ["s"])
    assert llm.calls[0].get("temperature") == 0.0  # temp=0 on the first attempt


# --- regression: adjudicator determinism (issue #1) -------------------------

def test_adjudicate_uses_temperature_zero():
    llm = MockLLM('{"verdict": "popular_confirmed", "authoritative_answer": "x", "why": "y"}')
    adjudicate(llm, "q", _STANCE, [{"predicate": "p", "value": "v"}], [])
    assert llm.calls[0].get("temperature") == 0.0


# --- regression: L1 snippet boilerplate strip (issue #4) --------------------

def test_l1_snippet_strips_nav_boilerplate():
    txt = "Skip to content Home About Menu Toggle   the DAT exam has four sections"
    out = L1ArticleIndex._snippet(txt, None)
    assert "Skip to content" not in out and "Menu Toggle" not in out
    assert "DAT exam has four sections" in out
    assert "  " not in out  # whitespace collapsed
