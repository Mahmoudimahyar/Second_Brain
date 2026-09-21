"""PV-5: query-scoped (faceted) sub-topic clustering.

"What are the interview-prep topics?" used to return the GLOBAL topic clusters — too
coarse. Instead, retrieve the facet's relevant docs (the query-scoped set) and cluster
THAT subset on the fly into named sub-topics, counted (reusing the stance kernel).

So "interview topics" yields the sub-topics *within interviews* (behavioral questions,
why-this-school, ethical scenarios, ...), each a real count over the retrieved docs with
its source-id set retained for drill-down — not 99 corpus-wide clusters.
"""

from __future__ import annotations

import re

from src.retrieval.stance import _parse_positions, classify_counted

# Facet/sub-topic intent: asks for the topics/themes WITHIN something, not an opinion.
_FACET_RE = re.compile(
    r"\b(sub-?topics?|topics?|themes?|subjects?|categories|aspects?|"
    r"what comes up|what do (?:people|applicants|students|they) (?:discuss|talk about)|"
    r"common (?:questions?|themes?|topics?|concerns?|issues?))\b", re.I)

# words to drop when distilling the facet's content terms for keyword retrieval
_FACET_STOP = {
    "what", "are", "is", "the", "a", "an", "common", "most", "topics", "topic", "themes",
    "theme", "subjects", "subject", "categories", "aspects", "aspect", "come", "comes",
    "up", "do", "people", "applicants", "applicant", "students", "student", "they",
    "discuss", "talk", "about", "of", "in", "for", "on", "and", "or", "to", "main",
    "key", "some", "list",
    # corpus-universal domain words — they match nearly every doc, so they don't help
    # scope a facet; dropping them lets the discriminative term (e.g. "interview") lead.
    "dental", "school", "schools", "college", "colleges", "university", "universities",
    "program", "programs", "dentistry", "dentist",
}

_SUBTOPIC_PROMPT = (
    "Forum excerpts related to this question:\n\"{q}\"\n\nExcerpts:\n{snips}\n\n"
    "Identify the 3-6 DISTINCT SUB-TOPICS / themes actually discussed in these excerpts "
    "(specific recurring subjects, not opinions or sentiment). Make them mutually distinct "
    "and collectively cover the excerpts.\n"
    'Return ONLY a JSON array: [{{"label": "<short sub-topic>", "description": "<one sentence>"}}].'
)


def is_facet_query(question: str) -> bool:
    """Does the question ask for the sub-topics/themes within a facet?"""
    return bool(_FACET_RE.search(question or ""))


def facet_terms(question: str) -> list[str]:
    """Content terms for keyword retrieval of the facet's docs (facet markers removed)."""
    toks = re.findall(r"[a-z][a-z\-]{2,}", (question or "").lower())
    return [t for t in toks if t not in _FACET_STOP][:6]


def derive_subtopics(llm, question: str, snippets: list[str], *, max_topics: int = 6,
                     attempts: int = 2) -> list[dict]:
    """LLM names 3-6 sub-topics from sample excerpts (no counts). Temp 0 then 0.3 retry."""
    snips = "\n".join(f"- {s[:200]}" for s in snippets[:40])
    prompt = _SUBTOPIC_PROMPT.format(q=question, snips=snips)
    for i in range(max(1, attempts)):
        try:
            r = llm.complete(prompt, schema=None, temperature=0.0 if i == 0 else 0.3)
            topics = _parse_positions(r.raw_text or "", max_topics)
            if topics:
                return topics
        except Exception:  # noqa: BLE001
            continue
    return []


def facet_distribution(
    store, llm, question: str, doc_ids: list[str], snippet_fn,
    *, sample: int = 40, min_sim: float = 0.12,
) -> dict:
    """Counted sub-topic distribution over a query-scoped doc set.

    Returns {subtopics: [{label, description, n, fraction, example_ids, doc_ids}],
    classified, unclear, n_total}.
    """
    if not doc_ids:
        return {"subtopics": [], "classified": 0, "n_total": 0, "note": "no evidence"}
    snip_map = snippet_fn(doc_ids[:sample])
    snippets = [t for t in (snip_map.get(d, "") for d in doc_ids[:sample]) if t]
    if not snippets:
        return {"subtopics": [], "classified": 0, "n_total": 0, "note": "no sample text"}
    topics = derive_subtopics(llm, question, snippets)
    if not topics:
        return {"subtopics": [], "classified": 0, "n_total": 0, "note": "no subtopics derived"}
    dist, classified, unclear, n_total = classify_counted(
        store, topics, doc_ids, min_sim=min_sim)
    return {"subtopics": dist, "classified": classified, "unclear": unclear,
            "n_total": n_total}
