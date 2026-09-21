"""Unified evidence recall + relevance filter for the Evidence Dossier (ED-3).

Broad-then-filter (decision #1): union candidates from complementary sources, dedupe
with provenance, then prune broad→precise. Honest counts (decision #2: always counted)
come from scoring the **full** population, never a sample.

Recall sources (no single one covers everything — verified 2026-06-18):
  - **graph (SDN)**: `graph_anchored_recall` — `MENTIONS_SCHOOL` is SDN-only, so the
    graph is the strong path for SDN evidence (exact structural population).
  - **text (reddit)**: FTS5 broad OR-match over `documents.sqlite` — reddit isn't
    entity-linked in the graph, so keyword recall + the similarity floor cover it.
  - **L1**: official Claims / ForumConsensus from the graph (trusted anchor).

Filter stages:
  A. drop no-text / no-vector (can't be cited evidence) + junk.
  B. semantic similarity floor (`EmbeddingStore`) — the workhorse: huge structural
     population → the slice actually about the question.
  C. LLM relevance gate on the borderline band only (cost-bounded).

Runs on the EC2 VM (graph parquet + documents.sqlite + embeddings co-located). Never
touches the local Kùzu graph.
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field

# Tier per source_type.
_TIER = {
    "sdn_post": "L5", "reddit_post": "L5", "reddit_comment": "L5",
    "l1_claim": "L1", "l1_page": "L1", "forum_consensus": "L5",
}


@dataclass
class Candidate:
    doc_id: str
    source_type: str
    tier: str
    recall_sources: set[str] = field(default_factory=set)  # {graph, fts5, l1}
    relevance: float | None = None  # cosine vs question (None = no vector)

    def to_dict(self) -> dict:
        return {
            "doc_id": self.doc_id, "source_type": self.source_type, "tier": self.tier,
            "recall_sources": sorted(self.recall_sources), "relevance": self.relevance,
        }


@dataclass
class RecallResult:
    question: str
    school_id: str | None
    sub_populations: dict[str, int] = field(default_factory=dict)  # graph/topic breakdown
    population: dict[str, int] = field(default_factory=dict)   # broad, per source_type
    relevant: dict[str, int] = field(default_factory=dict)     # after filter
    dropped: dict[str, int] = field(default_factory=dict)      # reason -> count
    kept: list[Candidate] = field(default_factory=list)        # ranked, relevant
    l1_articles: list = field(default_factory=list)            # official prose (ED-4)
    forum_doc_ids: list = field(default_factory=list)          # full L5 relevant set (ED-5 stance)
    relevant_total: int = 0
    borderline_gated_in: int = 0

    def to_dict(self) -> dict:
        return {
            "question": self.question, "school_id": self.school_id,
            "sub_populations": self.sub_populations,
            "population": self.population, "relevant": self.relevant,
            "relevant_total": self.relevant_total,
            "dropped": self.dropped, "borderline_gated_in": self.borderline_gated_in,
            "n_kept": len(self.kept), "n_l1_articles": len(self.l1_articles),
        }


_ACR_STOP = {"of", "the", "and", "at", "for", "in"}


def derive_aliases(canonical_name: str) -> list[str]:
    """Best-effort surface forms for a school name (production wires the canonical
    index; this covers the common acronym/prefix forms). NYU College of Dentistry →
    {full name, "new york university", "nyu", "nyucd"}."""
    name = (canonical_name or "").lower().strip()
    if not name:
        return []
    words = re.findall(r"[a-z]+", name)
    out: set[str] = {name}
    cut = len(words)
    for i, w in enumerate(words):
        if w in ("college", "school"):
            cut = i
            break
    prefix = [w for w in words[:cut] if w not in _ACR_STOP]
    if len(prefix) >= 2:
        out.add(" ".join(prefix))                       # "new york university"
        out.add("".join(w[0] for w in prefix))          # "nyu" / "ucsf"
    nonstop = [w for w in words if w not in _ACR_STOP]
    if 2 <= len(nonstop) <= 6:
        out.add("".join(w[0] for w in nonstop))         # "nyucd"
    return [a for a in out if len(a) >= 2]


_Q_STOP = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "at", "is", "are",
    "was", "were", "be", "do", "does", "did", "how", "what", "which", "who", "this",
    "that", "with", "as", "by", "from", "about", "than", "then", "you", "it", "my",
    "me", "we", "they", "should", "would", "could", "can", "will", "if", "any", "get",
    "vs", "school", "schools", "dental", "dentistry",
})


def _topic_term_list(question: str, aliases: list[str]) -> list[str]:
    """Question content terms with school-alias tokens stripped — the topic to match
    ('NYU tuition cost' → ['tuition','cost']). Generic dental words are dropped too,
    since every doc in this corpus is about dental school."""
    alias_tokens: set[str] = set()
    for a in aliases:
        alias_tokens.update(re.findall(r"[a-z]+", a.lower()))
    return [t for t in re.findall(r"[a-z0-9]+", question.lower())
            if t not in alias_tokens and t not in _Q_STOP and len(t) > 2]


def _reddit_school_set(link_conn, graph_reader, school_ids: list[str]) -> set[str]:
    """Reddit docs about the school: A (precomputed `reddit_school_link` table) ∪
    B (thread expansion of A-posts) ∪ C (claim-resolved posts). The expensive A is a
    millisecond table lookup now, not the 385s per-query FTS5."""
    a_docs: set[str] = set()
    if link_conn is not None and school_ids:
        marks = ",".join("?" * len(school_ids))
        a_docs = {r[0] for r in link_conn.execute(
            f"SELECT doc_id FROM reddit_school_link WHERE school_id IN ({marks})",  # noqa: S608
            school_ids,
        ).fetchall()}
    a_posts = [d for d in a_docs if d.startswith("reddit_post")]
    b_comments: set[str] = set()
    if a_posts and graph_reader is not None:
        b_comments = set(graph_reader.from_ids_for_targets("BELONGS_TO_THREAD", a_posts))
    c_posts: set[str] = set()
    if graph_reader is not None:
        c_posts = {p for p in graph_reader.claim_resolved_post_ids(school_ids)
                   if p.startswith("reddit_post")}
    return a_docs | b_comments | c_posts


def _topic_filter_by_text(docs_conn, doc_ids, terms: list[str]) -> set[str]:
    """Keep doc_ids whose text contains a topic term (word-boundary). **School-first**:
    we filter the small school set by fetching its text, never FTS5 over the 3.3M corpus
    (that was the 774s killer). Docs with no text (no row) drop out — they can't be cited."""
    if not doc_ids or not terms:
        return set()
    pat = re.compile(r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b", re.I)
    keep: set[str] = set()
    ids = list(doc_ids)
    for i in range(0, len(ids), 500):
        batch = ids[i:i + 500]
        marks = ",".join("?" * len(batch))
        for doc_id, text in docs_conn.execute(
            f"SELECT doc_id, text FROM documents WHERE doc_id IN ({marks})", batch,  # noqa: S608
        ):
            if text and pat.search(text):
                keep.add(doc_id)
    return keep


def assemble_candidates(
    question: str,
    school_id: str | None,
    *,
    graph_reader=None,
    docs_conn: sqlite3.Connection | None = None,
    link_conn: sqlite3.Connection | None = None,
    l1_index=None,
) -> tuple[dict[str, Candidate], dict[str, int], list]:
    """Assemble the candidate pool with the **school ∩ topic** gate applied.

    school = structure (SDN: graph `MENTIONS_SCHOOL`+threads; reddit: precomputed
    `reddit_school_link` A ∪ graph B/C). topic = word-boundary term match on the
    school set's text (school-first; no corpus FTS5). Counts are exact set arithmetic.
    Official L1 article prose (ED-4) is retrieved via `l1_index` and returned alongside.
    """
    pool: dict[str, Candidate] = {}
    meta: dict[str, int] = {}
    l1_articles: list = []

    def _add(doc_id: str, source_type: str, src: str) -> None:
        c = pool.get(doc_id)
        if c is None:
            pool[doc_id] = c = Candidate(doc_id, source_type, _TIER.get(source_type, "L5"))
        c.recall_sources.add(src)

    aliases: list[str] = []
    school_ids: list[str] = []
    if graph_reader is not None and school_id:
        school_ids = graph_reader.same_as_closure(school_id)
        aliases = derive_aliases(graph_reader.node_props(school_id).get("canonical_name", ""))
        meta["n_aliases"] = len(aliases)

    terms = _topic_term_list(question, aliases)

    if graph_reader is not None and school_id and docs_conn is not None:
        from src.retrieval.graph_recall import graph_anchored_recall  # noqa: PLC0415

        # SDN: graph school set, topic-filtered by text.
        gc = graph_anchored_recall(graph_reader, school_id, post_cap=50_000, member_cap=300_000)
        sdn_school = set(gc.candidate_doc_ids())
        sdn_rel = _topic_filter_by_text(docs_conn, sdn_school, terms)
        meta["sdn_school"] = len(sdn_school)
        meta["sdn_relevant"] = len(sdn_rel)
        for did in sdn_rel:
            _add(did, "sdn_post", "graph+text")
        for did in gc.l1_claim_ids:
            _add(did, "l1_claim", "l1")
        for did in gc.consensus_ids:
            _add(did, "forum_consensus", "l1")

        # Reddit: A∪B∪C school set, topic-filtered by text.
        reddit_school = _reddit_school_set(link_conn, graph_reader, school_ids)
        reddit_rel = _topic_filter_by_text(docs_conn, reddit_school, terms)
        meta["reddit_school"] = len(reddit_school)
        meta["reddit_relevant"] = len(reddit_rel)
        for did in reddit_rel:
            st = "reddit_post" if did.startswith("reddit_post") else "reddit_comment"
            _add(did, st, "reddit_scope")
    else:
        # No school resolved (process/general question). Corpus-wide forum recall is
        # unscoped + slow (a 1.95M-comment FTS5 scan), and forum *opinion* without a
        # school is out of V1 scope — process questions are answered by the L1 official
        # prose retrieved below. (Ask about a specific school for forum opinion.)
        meta["no_school"] = 1

    # ED-4: official L1 article prose (authoritative; semantic-relevance gated).
    if l1_index is not None and terms:
        arts = l1_index.retrieve(terms, school_ids, top_k=8, query_text=question)
        l1_articles = [a.__dict__ for a in arts]
        meta["l1_articles"] = len(arts)
        for a in arts:
            _add(a.chunk_id, "l1_page", "l1_article")

    return pool, meta, l1_articles


def recall_and_filter(
    question: str,
    school_id: str | None,
    *,
    graph_reader,
    store,
    docs_conn: sqlite3.Connection,
    link_conn: sqlite3.Connection | None = None,
    l1_index=None,
    floor: float = 0.45,
    band: float = 0.07,
    llm=None,
    llm_gate_cap: int = 60,
    display_k: int = 40,
    scored_cap: int = 6_000,
) -> RecallResult:
    """Full ED-3/4 pipeline. Counts are exact set arithmetic (school footprint →
    school∩topic); the embedding floor only ranks a bounded subset for display;
    official L1 article prose (ED-4) is surfaced via `l1_index`."""
    pool, meta, l1_articles = assemble_candidates(
        question, school_id, graph_reader=graph_reader, docs_conn=docs_conn,
        link_conn=link_conn, l1_index=l1_index,
    )
    res = RecallResult(question=question, school_id=school_id)
    res.sub_populations = meta
    res.l1_articles = l1_articles

    # Funnel (exact, no scoring): school footprint → school ∩ topic.
    res.population = {  # "about this school" (any topic)
        "sdn_post": meta.get("sdn_school", 0),
        "reddit": meta.get("reddit_school", 0),
    }
    res.relevant = dict(Counter(c.source_type for c in pool.values()))  # school ∩ topic
    res.relevant_total = len(pool)

    l1 = [c for c in pool.values() if c.tier == "L1"]
    forum = [c for c in pool.values() if c.tier == "L5"]
    res.forum_doc_ids = [c.doc_id for c in forum]  # full relevant set for ED-5 stance

    # Display ranking: score only a bounded subset (counts above are already exact).
    scored = forum[:scored_cap]
    res.dropped["pool_unscored_for_display"] = max(0, len(forum) - len(scored))
    part = store.filter_by_floor([c.doc_id for c in scored], question, floor=floor, band=band)
    score_by_id = {did: s for did, s in (*part["keep"], *part["borderline"], *part["drop"])}
    for c in scored:
        c.relevance = score_by_id.get(c.doc_id)
    display_ids = {did for did, _ in part["keep"]}

    # Stage C: LLM relevance gate on the borderline band only (cost-bounded).
    border = part["borderline"][:llm_gate_cap]
    gated_in = 0
    if llm is not None and border:
        snippets = _snippets(docs_conn, [did for did, _ in border])
        for did, _ in border:
            text = snippets.get(did, "")
            if text and _llm_relevant(llm, question, text):
                display_ids.add(did)
                gated_in += 1
    res.borderline_gated_in = gated_in

    display = [c for c in scored if c.doc_id in display_ids]
    display.sort(key=lambda c: -(c.relevance or 0.0))
    res.kept = (l1 + display)[:display_k]
    return res


def _snippets(conn: sqlite3.Connection, doc_ids: list[str], *, chars: int = 300) -> dict[str, str]:
    if not doc_ids:
        return {}
    out: dict[str, str] = {}
    for i in range(0, len(doc_ids), 400):
        chunk = doc_ids[i:i + 400]
        marks = ",".join("?" * len(chunk))
        rows = conn.execute(
            f"SELECT doc_id, substr(text,1,{int(chars)}) FROM documents WHERE doc_id IN ({marks})",  # noqa: S608
            chunk,
        ).fetchall()
        out.update(dict(rows))
    return out


def _llm_relevant(llm, question: str, snippet: str) -> bool:
    prompt = (
        "Is the following forum text directly relevant to answering the question? "
        "Answer only 'yes' or 'no'.\n\n"
        f"QUESTION: {question}\nTEXT: {snippet[:300]}\n\nANSWER:"
    )
    try:
        r = llm.complete(prompt, schema=None)
        return (r.raw_text or "").strip().lower().startswith("y")
    except Exception:  # noqa: BLE001
        return False
