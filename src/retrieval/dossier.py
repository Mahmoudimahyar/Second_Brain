"""Evidence Dossier Engine — the productionized answer path (ED-3 … ED-8).

Loads the bundle artifacts (parquet graph, embeddings, documents.sqlite,
reddit_school_link.sqlite, L1 article index) + an LLM, and answers a question with a
full **adjudicated evidence dossier**:

  - typed evidence counts (school ∩ topic), exact set arithmetic
  - most-reliable official sources (L1 Claims + L1 article prose, with URLs)
  - counted opinion distribution (real 80/15/5 — classified, not estimated)
  - popular-vs-correct verdict (L1-anchored; abstains without an official anchor)
  - drill-down sources with thread context (ED-7) + full ids for pagination
  - calibrated abstention (ED-8)

Runs where the bundle lives (EC2 / shipped bundle). The web route injects one shared
instance. All heavy I/O is parquet/duckdb/sqlite/embeddings — never local Kùzu.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from src.er.alias_expansion import expand_aliases
from src.retrieval.adjudicator import adjudicate
from src.retrieval.embedding_store import EmbeddingStore
from src.retrieval.evidence_recall import _reddit_school_set, _snippets, recall_and_filter
from src.retrieval.graph_recall import ParquetGraphReader
from src.retrieval.l1_retrieval import L1ArticleIndex
from src.retrieval.facets import facet_distribution, facet_terms, is_facet_query
from src.retrieval.planner import (
    SchoolMetrics, execute_plan, is_ranking_query, plan_query,
)
from src.retrieval.provenance import ProvenanceStore, build_distribution
from src.retrieval.rendering import (
    allowed_numbers, guard_narration, render_facets, render_grounded_answer, render_ranking,
)
from src.retrieval.stance import stance_distribution

_MIN_EVIDENCE = 3
_MIN_MAJORITY = 0.40
# A proper noun adjacent to a school-type word ("Zzqx Dental College") — used to detect
# a question that names a specific school the resolver could not map to a known entity.
_SCHOOL_NAME_RE = re.compile(
    r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]+)*\s+(?:Dental|College|University|School|Institute)\b"
)
_ALIAS_BLOCKLIST = {"case", "new", "old", "union", "pacific", "western", "southern",
                    "central", "national", "general", "health", "oral", "medical"}
_REDDIT_BASE = "https://www.reddit.com"


def _full_url(doc_id: str, url: str, thread_id: str, postmap: dict[str, str]) -> str:
    """Best clickable URL for a source. Reddit posts store a relative permalink;
    reddit comments store none (rebuilt from the parent post permalink + comment id);
    SDN stores absolute URLs."""
    if url:
        return _REDDIT_BASE + url if url.startswith("/") else url
    if doc_id.startswith("reddit_comment:") and thread_id in postmap:
        purl = postmap[thread_id]
        base = (_REDDIT_BASE + purl if purl.startswith("/") else purl).rstrip("/")
        return f"{base}/{doc_id.split(':')[-1]}/"
    return ""


class EvidenceDossierEngine:
    def __init__(self, bundle_dir: str | Path, *, llm=None) -> None:
        base = Path(bundle_dir)
        self.base = base
        nodes = str(base / "graph" / "nodes.parquet")
        edges = str(base / "graph" / "edges.parquet")
        self.reader = ParquetGraphReader(nodes, edges)
        self.store = EmbeddingStore(str(base / "embeddings"))
        self.l1 = L1ArticleIndex(nodes, edges, embedder=self.store,
                                 emb_dir=str(base / "embeddings"))
        self.docs = sqlite3.connect(str(base / "raw" / "documents.sqlite"), check_same_thread=False)
        link_path = base / "reddit_school_link.sqlite"
        self.link = sqlite3.connect(str(link_path), check_same_thread=False) if link_path.exists() else None
        self.metrics = SchoolMetrics(base / "school_metrics.sqlite")   # PV-4 ranking ops
        self._llm = llm
        self.prov = ProvenanceStore()
        self._alias_to_school = self._build_alias_map()

    # -- provenance hydration (PV-1) ----------------------------------------

    def _hydrate(self, ids: list[str]) -> list[dict]:
        """doc_id -> {url, snippet, ...} from documents.sqlite (for drill-down).

        Resolves clickable URLs: reddit comments store none, so the comment permalink is
        rebuilt from the parent post's permalink (via thread_id) + comment id.
        """
        if not ids:
            return []
        raw: list[tuple] = []
        for i in range(0, len(ids), 400):
            batch = ids[i:i + 400]
            marks = ",".join("?" * len(batch))
            raw.extend(self.docs.execute(
                f"SELECT doc_id, doc_type, url, substr(text,1,300), score, thread_id "  # noqa: S608
                f"FROM documents WHERE doc_id IN ({marks})", batch,
            ).fetchall())
        need = sorted({r[5] for r in raw
                       if (not r[2]) and r[0].startswith("reddit_comment:") and r[5]})
        postmap: dict[str, str] = {}
        for i in range(0, len(need), 400):
            batch = need[i:i + 400]
            marks = ",".join("?" * len(batch))
            for d, u in self.docs.execute(
                f"SELECT doc_id, url FROM documents WHERE doc_id IN ({marks})", batch):  # noqa: S608
                if u:
                    postmap[d] = u
        return [{"doc_id": r[0], "source_type": r[1],
                 "url": _full_url(r[0], r[2], r[5], postmap),
                 "snippet": r[3], "score": r[4], "thread_id": r[5]} for r in raw]

    def _school_sentiment_ids(self, school_id: str, label: str) -> list[str]:
        """The exact reddit-comment ids for one verdict bucket of a school (on demand)."""
        closure = self.reader.same_as_closure(school_id)
        rset = _reddit_school_set(self.link, self.reader, closure)
        rcomments = [d for d in rset if d.startswith("reddit_comment")]
        return self.reader.sentiment_for(rcomments).get(label, [])

    def sources(self, stat_id: str | None = None, *, school: str | None = None,
                label: str = "positive", offset: int = 0, limit: int = 50) -> dict:
        """Drill-down: the exact source posts/comments behind a statistic (paginated).

        Either a `stat_id` from a returned statistic, or (`school`, `label`) for a ranking
        row's sentiment bucket (computed on demand so rankings stay fast).
        """
        if stat_id:
            rec = self.prov.get(stat_id)
            if rec is None:
                return {"error": "unknown or expired stat_id", "stat_id": stat_id}
            ids, meta = rec["ids"], {"stat_id": stat_id, "label": rec["label"],
                                     "method": rec["method"], "source_kind": rec["source_kind"]}
        elif school:
            ids = self._school_sentiment_ids(school, label)
            meta = {"school": school, "label": label, "source_kind": "reddit_comment",
                    "method": f"{label} SentimentAnnotation over the school's reddit comments"}
        else:
            return {"error": "provide stat_id or school"}
        page = ids[offset:offset + limit]
        return {**meta, "total": len(ids), "offset": offset, "limit": limit,
                "sources": self._hydrate(page)}

    def _ranking_answer(self, question: str, ranked: dict) -> dict:
        """Wrap an executed plan as a dossier answer (PV-4): deterministic table +
        per-row lazy drill-down to the exact comments behind each sentiment %."""
        for r in ranked["ranking"]:
            r["drill_down"] = (f"/api/v1/dossier/sources?school={r['school_id']}"
                               f"&label=positive")
        return {
            "answered": True, "question": question, "mode": "ranking",
            "grounded_answer": render_ranking(ranked),
            "plan": ranked["plan"], "ranking": ranked["ranking"],
            "filtered_claims": [], "provenance": {"opinion": [], "sentiment": []},
            "abstain_reason": None,
        }

    def research(self, question: str) -> dict:
        """The scientific answer path (RP-3): routes the question to an estimand and runs
        the full research protocol — measured estimates with thread-clustered CIs, shrinkage,
        measurement-error sensitivity, robustness, temporal trend, cohort split, bias label,
        and provenance. Returns a ResearchDossier (reasoning log + final_answer)."""
        from src.research.protocol import ResearchProtocol  # noqa: PLC0415 — avoid import cycle

        return ResearchProtocol(self).run(question)

    def _fts_facet(self, question: str, *, limit: int = 3000) -> list[str]:
        """Forum docs matching the facet's content terms (FTS5, query-scoped)."""
        terms = facet_terms(question)
        if not terms:
            return []
        # Quote each term so FTS5 treats hyphens/punctuation literally ("pre-dental" would
        # otherwise be parsed as a column filter and raise); rank-order for relevance.
        match = " OR ".join(f'"{t}"' for t in terms)
        try:
            rows = self.docs.execute(
                "SELECT d.doc_id FROM docs_fts f JOIN documents d ON f.rowid=d.rowid "
                "WHERE docs_fts MATCH ? AND d.doc_type IN "
                "('reddit_post','reddit_comment','sdn_post') ORDER BY rank LIMIT ?",
                (match, int(limit)),
            ).fetchall()
        except sqlite3.Error:
            return []
        return [r[0] for r in rows]

    def _facet_answer(self, question: str, sid: str | None) -> dict | None:
        """PV-5: cluster the query-scoped doc set into counted sub-topics (or None to fall
        through to the normal path when there's too little to cluster)."""
        if sid:
            res = recall_and_filter(
                question, sid, graph_reader=self.reader, store=self.store,
                docs_conn=self.docs, link_conn=self.link, l1_index=self.l1,
                llm=None, display_k=25)
            doc_ids = res.forum_doc_ids
        else:
            doc_ids = self._fts_facet(question)
        if len(doc_ids) < _MIN_EVIDENCE:
            return None
        facets = facet_distribution(
            self.store, self._llm, question, doc_ids,
            lambda ids: _snippets(self.docs, ids))
        subtopics = facets.get("subtopics", [])
        if not subtopics:
            return None
        fstats = build_distribution(
            self.prov, prefix=f"{sid or question}:facet",
            buckets={p["label"]: p["doc_ids"] for p in subtopics},
            source_kind="forum", method="query-scoped sub-topic clustering")
        return {
            "answered": True, "question": question, "mode": "facets", "school_id": sid,
            "grounded_answer": render_facets(question, facets),
            "subtopics": [{k: v for k, v in s.items() if k != "doc_ids"} for s in subtopics],
            "provenance": {"facets": [s.to_dict() for s in fstats],
                           "opinion": [], "sentiment": []},
            "filtered_claims": [], "abstain_reason": None,
            "n_docs_clustered": facets.get("classified", 0),
        }

    # -- school resolution ---------------------------------------------------

    def _build_alias_map(self) -> list[tuple[str, str]]:
        """alias(lower) -> canonical school rep, sorted longest-first for greedy match.
        SAME_AS-unioned so dup nodes share one rep; ambiguous/common aliases dropped."""
        import json  # noqa: PLC0415

        parent: dict[str, str] = {}

        def find(x: str) -> str:
            parent.setdefault(x, x)
            root = x
            while parent[root] != root:
                root = parent[root]
            while parent[x] != root:
                parent[x], x = root, parent[x]
            return root

        for a, b in self.reader.con.execute(
            "SELECT from_id, to_id FROM edges WHERE label='SAME_AS'"
        ).fetchall():
            parent.setdefault(a, a)
            parent.setdefault(b, b)
            ra, rb = find(a), find(b)
            if ra != rb:
                if rb.startswith("school:") and not ra.startswith("school:"):
                    ra, rb = rb, ra
                parent[rb] = ra

        alias_map: dict[str, set[str]] = {}
        for sid, pj in self.reader.con.execute(
            "SELECT id, properties_json FROM nodes WHERE label='School'"
        ).fetchall():
            name = (json.loads(pj).get("canonical_name", "") if pj else "")
            rep = find(sid)
            forms = {ea.alias_text.lower() for ea in expand_aliases(sid, name)}
            if name:
                forms.add(name.lower())
            for a in forms:
                if len(a) >= 3 and a not in _ALIAS_BLOCKLIST:
                    alias_map.setdefault(a, set()).add(rep)
        clean = [(a, next(iter(s))) for a, s in alias_map.items() if len(s) == 1]
        clean.sort(key=lambda x: -len(x[0]))  # greedy longest-match
        return clean

    def resolve_school(self, question: str) -> str | None:
        q = question.lower()
        for alias, sid in self._alias_to_school:
            if re.search(r"\b" + re.escape(alias) + r"\b", q):
                return sid
        return None

    # -- L1 facts + drill-down ----------------------------------------------

    def _l1_facts(self, claim_ids: list[str]) -> list[dict]:
        out: list[dict] = []
        seen: set[tuple[str, str]] = set()  # dedup SAME_AS-duplicated claims by (predicate, value)
        for cid in claim_ids[:24]:
            p = self.reader.node_props(cid)
            if not p:
                continue
            pred = p.get("predicate_canonical") or p.get("predicate") or "claim"
            val = p.get("object_value", p.get("value", ""))
            key = (str(pred), str(val))
            if key in seen:
                continue
            seen.add(key)
            out.append({"predicate": pred, "value": val,
                        "url": p.get("source_url", ""), "doc_id": cid})
            if len(out) >= 12:
                break
        return out

    def _source_items(self, candidates: list, l1_articles: list[dict]) -> list[dict]:
        """ED-7 drill-down: rich, thread-aware source rows for the display set."""
        art_by_chunk = {a["chunk_id"]: a for a in l1_articles}
        forum_ids = [c.doc_id for c in candidates
                     if c.source_type in ("sdn_post", "reddit_post", "reddit_comment")]
        rows: dict[str, dict] = {}
        for i in range(0, len(forum_ids), 400):
            batch = forum_ids[i:i + 400]
            marks = ",".join("?" * len(batch))
            for r in self.docs.execute(
                f"SELECT doc_id, doc_type, source, url, title, substr(text,1,300), score, "  # noqa: S608
                f"thread_id, parent_id FROM documents WHERE doc_id IN ({marks})", batch,
            ):
                rows[r[0]] = {
                    "doc_id": r[0], "source_type": r[1], "source": r[2], "url": r[3],
                    "title": r[4], "snippet": r[5], "score": r[6],
                    "thread_id": r[7], "parent_id": r[8],
                }
        items: list[dict] = []
        for c in candidates:
            if c.source_type in ("sdn_post", "reddit_post", "reddit_comment"):
                it = rows.get(c.doc_id) or {"doc_id": c.doc_id, "source_type": c.source_type}
                it["tier"] = "L5"
                it["relevance"] = round(c.relevance, 3) if c.relevance is not None else None
                items.append(it)
            elif c.source_type == "l1_page":
                a = art_by_chunk.get(c.doc_id, {})
                items.append({"doc_id": c.doc_id, "source_type": "l1_page", "tier": "L1",
                              "url": a.get("url", ""), "title": a.get("title", ""),
                              "domain": a.get("domain", ""), "snippet": a.get("snippet", "")})
            elif c.source_type == "l1_claim":
                p = self.reader.node_props(c.doc_id)
                items.append({"doc_id": c.doc_id, "source_type": "l1_claim", "tier": "L1",
                              "snippet": f"{p.get('predicate_canonical', p.get('predicate', 'claim'))}: "
                                         f"{p.get('object_value', p.get('value', ''))}",
                              "url": p.get("source_url", "")})
            elif c.source_type == "forum_consensus":
                p = self.reader.node_props(c.doc_id)
                items.append({"doc_id": c.doc_id, "source_type": "forum_consensus", "tier": "L5",
                              "snippet": f"{p.get('metric', '')}: median={p.get('median', '')} "
                                         f"n={p.get('n', '')}"})
        return items

    # -- abstention ----------------------------------------------------------

    @staticmethod
    def _abstain(relevant_total: int, stance: dict, verdict: dict) -> str | None:
        if relevant_total < _MIN_EVIDENCE:
            return f"insufficient evidence (only {relevant_total} relevant sources)"
        positions = stance.get("positions", []) if stance else []
        if positions:
            top = max((p.get("fraction", 0.0) for p in positions), default=0.0)
            if top < _MIN_MAJORITY:
                return f"no clear majority opinion (top stance {top:.0%})"
        if verdict.get("verdict") == "needs_research":
            return "evidence too thin/conflicting to adjudicate"
        return None

    # -- main ----------------------------------------------------------------

    def answer(self, question: str, *, display_k: int = 25) -> dict:
        sid = self.resolve_school(question)
        # PV-4: a cross-school ranking/comparison ("cheapest schools applicants also
        # like", "worst reviewed schools") -> typed plan executed deterministically over
        # the precomputed school_metrics, rendered as a table the LLM can't reorder.
        if is_ranking_query(question):
            plan = plan_query(self._llm, question)
            if plan.get("ops"):
                ranked = execute_plan(plan, self.metrics)
                if ranked and ranked.get("ranking"):
                    return self._ranking_answer(question, ranked)
        # PV-5: a faceted sub-topic query ("interview-prep topics") -> cluster the
        # query-scoped docs into counted sub-topics, not the global clusters.
        if is_facet_query(question):
            fa = self._facet_answer(question, sid)
            if fa is not None:
                return fa
        # NB: llm=None for recall — counts are exact set arithmetic and display is
        # floor-ranked, so the per-doc borderline LLM gate (up to 60 sequential calls)
        # adds only marginal display polish while bursting the rate limit and starving
        # the stance/adjudicate calls. The two LLM calls that matter (stance positions +
        # adjudication) run below. The gate stays available via recall_and_filter(llm=).
        res = recall_and_filter(
            question, sid, graph_reader=self.reader, store=self.store,
            docs_conn=self.docs, link_conn=self.link, l1_index=self.l1,
            llm=None, display_k=display_k,
        )
        l1_claim_ids = [c.doc_id for c in res.kept if c.source_type == "l1_claim"]
        l1_facts = self._l1_facts(l1_claim_ids)

        stance = stance_distribution(
            self.store, self._llm, question, res.forum_doc_ids,
            lambda ids: _snippets(self.docs, ids),
        )
        verdict = adjudicate(self._llm, question, stance, l1_facts, res.l1_articles)
        sources = self._source_items(res.kept, res.l1_articles)
        abstain = self._abstain(res.relevant_total, stance, verdict)
        # Question named a specific school we couldn't resolve → don't answer from
        # generic L1 matches; abstain (e.g. "Is Zzqx Dental College good?").
        if sid is None and _SCHOOL_NAME_RE.search(question):
            abstain = ("could not identify the school named in the question; "
                       "no school-specific evidence available")

        # Consistency: an abstention must not also present a confident answer. Expose an
        # explicit `answered` flag and suppress the verdict's authoritative_answer when
        # abstaining (the abstain_reason is the answer; sources remain for inspection).
        answered = abstain is None
        if not answered and verdict.get("authoritative_answer"):
            verdict = {**verdict, "authoritative_answer": None, "confidence": "low"}

        # PV-1: per-statistic provenance — every number carries its exact source-id set.
        opinion_stats = []
        if stance.get("positions"):
            opinion_stats = build_distribution(
                self.prov, prefix=f"{sid or question}:opinion",
                buckets={p["label"]: p.get("doc_ids", []) for p in stance["positions"]},
                source_kind="forum", method="stance clustering over relevant forum docs")
        sentiment_stats = []
        if sid:
            rset = _reddit_school_set(self.link, self.reader, self.reader.same_as_closure(sid))
            rcomments = [d for d in rset if d.startswith("reddit_comment")]
            sent_buckets = self.reader.sentiment_for(rcomments)
            if sent_buckets:
                sentiment_stats = build_distribution(
                    self.prov, prefix=f"{sid}:sentiment", buckets=sent_buckets,
                    source_kind="reddit_comment",
                    method="SentimentAnnotation verdict over the school's reddit comments")

        prov_dict = {
            "opinion": [s.to_dict() for s in opinion_stats],
            "sentiment": [s.to_dict() for s in sentiment_stats],
        }

        # PV-2: anti-fabrication. Guard the LLM verdict prose against the counted facts
        # (drop sentences with unsupported statistics), then assemble a deterministic
        # grounded answer the LLM cannot reorder or invent.
        allowed = allowed_numbers({"provenance": prov_dict, "evidence_counts": res.relevant,
                                   "l1_facts": l1_facts, "relevant_total": res.relevant_total})
        filtered_claims: list[str] = []
        for key in ("authoritative_answer", "rationale"):
            if verdict.get(key):
                clean, dropped = guard_narration(verdict[key], allowed)
                if dropped:
                    verdict = {**verdict, key: clean or None}
                    filtered_claims += dropped
        grounded = render_grounded_answer({
            "answered": answered, "abstain_reason": abstain, "l1_facts": l1_facts,
            "provenance": prov_dict, "verdict": verdict})

        return {
            "answered": answered,
            "question": question,
            "grounded_answer": grounded,                 # deterministic, faithful surface
            "filtered_claims": filtered_claims,          # LLM prose dropped as unsupported
            "provenance": prov_dict,
            "school_id": sid,
            "evidence_counts": res.relevant,            # typed counts (school ∩ topic)
            "evidence_footprint": res.population,        # "about this school" (any topic)
            "funnel": res.sub_populations,
            "relevant_total": res.relevant_total,
            "most_reliable": {"l1_facts": l1_facts, "l1_articles": res.l1_articles[:5]},
            "opinion_distribution": stance,              # counted 80/15/5
            "verdict": verdict,                          # popular vs correct
            "abstain_reason": abstain,
            "sources": sources,                          # drill-down (display_k)
            "all_relevant_ids": res.forum_doc_ids,       # full set for pagination
        }
