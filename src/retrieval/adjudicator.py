"""ED-6: L1-anchored adjudicator — separate *popular* from *correct*.

Decision #3 (`project_evidence_dossier`): L1 official sources (ADEA/ADA/CDA + official
data) are trusted ground truth. The verdict follows L1 when the popular forum view
contradicts it; it **abstains** ('needs_research' / 'no_official_source') when no L1
anchor exists. The LLM judges *within* these rules — it cannot override L1, and it is
never asked to invent a correctness claim the official record doesn't support.
"""

from __future__ import annotations

import json
import re

VERDICTS = frozenset({
    "popular_confirmed",   # official data agrees with the dominant forum view
    "popular_is_wrong",    # official data contradicts the dominant forum view
    "combination",         # correct answer combines multiple positions / it depends
    "no_official_source",  # no L1 evidence bears on the question — forum-only
    "needs_research",      # evidence too thin/conflicting to adjudicate
})

_PROMPT = (
    "You are an evidence adjudicator for dental-school applicants. Your job is to separate "
    "the POPULAR forum view from the CORRECT answer.\n"
    "RULE: the OFFICIAL (L1) sources below — ADEA/ADA/CDA and official data — are authoritative "
    "ground truth. If the popular forum view contradicts the official record, the correct answer "
    "FOLLOWS the official record (verdict 'popular_is_wrong'). Never assert a correctness claim the "
    "official record does not support.\n\n"
    'QUESTION: "{q}"\n\n'
    "POPULAR FORUM POSITIONS (counted over the relevant corpus):\n{positions}\n\n"
    "OFFICIAL L1 DATA (structured facts):\n{facts}\n\n"
    "OFFICIAL L1 ARTICLES (authoritative prose):\n{articles}\n\n"
    "Return ONLY JSON:\n"
    '{{"verdict": one of [popular_confirmed, popular_is_wrong, combination], '
    '"authoritative_answer": "<1-2 sentences grounded ONLY in the official data/articles above>", '
    '"popular_answer": "<the dominant forum position>", '
    '"why": "<one sentence; if the official answer differs from the popular one, say so explicitly>"}}'
)


def _fmt_positions(stance: dict) -> str:
    pos = stance.get("positions", []) if stance else []
    if not pos:
        return "(none)"
    return "\n".join(
        f"- {p['label']} — {p.get('fraction', 0):.0%} ({p.get('n', 0)} docs): {p.get('description', '')}"
        for p in pos
    )


def _fmt_facts(l1_facts: list[dict]) -> str:
    if not l1_facts:
        return "(none)"
    return "\n".join(
        f"- {f.get('predicate', '?')}: {f.get('value', '')}" + (f"  [{f['url']}]" if f.get("url") else "")
        for f in l1_facts[:12]
    )


def _fmt_articles(l1_articles: list[dict]) -> str:
    if not l1_articles:
        return "(none)"
    return "\n".join(
        f"- [{a.get('domain', '')}] {a.get('title', '')[:70]}: {a.get('snippet', '')[:180]}"
        for a in l1_articles[:5]
    )


def adjudicate(
    llm, question: str, stance: dict, l1_facts: list[dict], l1_articles: list[dict],
) -> dict:
    """Render the popular-vs-correct verdict. L1-anchored; abstains without an L1 anchor."""
    popular = None
    if stance and stance.get("positions"):
        popular = stance["positions"][0]["label"]

    # No official anchor → do not manufacture a correctness verdict (decision #3).
    if not l1_facts and not l1_articles:
        return {
            "verdict": "no_official_source",
            "authoritative_answer": None,
            "popular_answer": popular,
            "why": "No L1 official source covers this question — forum consensus only; "
                   "further research against primary sources is needed.",
        }

    if llm is None:
        return {
            "verdict": "needs_research", "authoritative_answer": None,
            "popular_answer": popular, "why": "Adjudication LLM unavailable.",
        }

    prompt = _PROMPT.format(
        q=question, positions=_fmt_positions(stance),
        facts=_fmt_facts(l1_facts), articles=_fmt_articles(l1_articles),
    )
    try:
        r = llm.complete(prompt, schema=None, temperature=0.0)
        m = re.search(r"\{.*\}", (r.raw_text or "").strip(), re.DOTALL)
        if not m:
            raise ValueError("no JSON in adjudication response")
        obj = json.loads(m.group(0))
        verdict = obj.get("verdict")
        if verdict not in VERDICTS:
            verdict = "combination"
        return {
            "verdict": verdict,
            "authoritative_answer": obj.get("authoritative_answer"),
            "popular_answer": obj.get("popular_answer") or popular,
            "why": obj.get("why", ""),
        }
    except Exception:  # noqa: BLE001
        return {
            "verdict": "needs_research", "authoritative_answer": None,
            "popular_answer": popular, "why": "Adjudication failed to parse.",
        }
