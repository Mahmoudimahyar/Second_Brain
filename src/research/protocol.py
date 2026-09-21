"""RP-3: the research protocol runner — every answer goes through this.

`ResearchProtocol.run(question)` routes the question to an estimand, retrieves the
query-scoped evidence, assigns each doc to a bucket (graph sentiment, or LLM-named +
embedding-counted stance/topics), enriches with thread/author/year/cohort, then applies
the SAME statistical protocol to every estimand:

  proportion + Wilson CI + thread-clustered bootstrap CI + effective N
  -> consensus index (stance) / shrinkage (rankings)
  -> measurement-error sensitivity band (Rogan-Gladen; no human gold -> a range, not a point)
  -> robustness perturbation -> temporal trend -> cohort split -> bias label -> provenance.

Output is a ResearchDossier dict: a full reasoning log + every number with its CI and its
stat_id drill-down + a deterministic final answer. No number is produced by the LLM.
"""

from __future__ import annotations

import re

from src.research import stats
from src.research.calibration import CalibrationStore, calibrated_prevalence
from src.research.clustering import kmeans_topics, top_cluster_fraction
from src.research.criteria import ConceptCriteria
from src.research.enrich import (
    clusters_for, cohort_of, enrich_items, extract_prices, is_junk, subreddit_of,
)
from src.research.positions import PositionCache, _key, stable_positions
from src.research.signals import compute_signals, minmax_normalize
from src.retrieval.evidence_recall import _reddit_school_set, _snippets, recall_and_filter
from src.retrieval.planner import execute_plan, plan_query
from src.retrieval.provenance import build_distribution
from src.retrieval.stance import classify_counted

_MIN_EVIDENCE = 3
_MONTHS = ("january february march april may june july august september october "
           "november december").split()
_BIAS = ("Forum users are a self-selected, vocal subset of applicants; complaints are "
         "over-represented (negativity bias) and posters skew toward the anxious/engaged. "
         "Read proportions as directional, and sentiment as a LOWER bound on satisfaction.")


def _step(stage: str, detail: str, data: object = None) -> dict:
    return {"stage": stage, "detail": detail, "data": data}


def classify_estimand(question: str) -> tuple[str, dict]:
    """Route a question to one estimand + detect temporal/segment/price modifiers."""
    q = (question or "").lower()
    flags = {
        "temporal": bool(re.search(r"\b(over time|trend|each year|by year|by month|history|"
                                   r"used to|nowadays|201\d|202\d)\b", q)
                         or any(m in q for m in _MONTHS)),
        "segment": bool(re.search(r"\b(pre-?dental|dental student|specialt|omfs|endo|"
                                  r"resident|cohort|segment| vs\.? )\b", q)),
        "price": bool(re.search(r"\b(how much|pay|paying|price|pricing|afford|\$|worth paying|"
                                r"willing to pay|comfortable)\b", q)),
    }
    # ranking is school-comparison-specific (it needs the school_metrics table); a bare
    # "top 5 use cases" must NOT route here.
    ranking = bool(
        re.search(r"\b(cheapest|most expensive|priciest|lowest tuition|highest tuition|afford)\b", q)
        or re.search(r"\b(worst|best|highest|lowest|top)\b.{0,25}\b(schools?|reviewed|rated|"
                     r"sentiment|reputation)\b", q)
        or re.search(r"\bwhich schools?\b", q)
        or re.search(r"\brank(ing|ed)?\b.{0,20}schools?", q))
    # a polarity contrast ("praise vs criticize", "pros and cons") -> sentiment-split topics
    contrast = bool(re.search(
        r"praise.{0,15}critic|critic.{0,15}praise|pros and cons|pros.{0,8}cons|"
        r"like.{0,10}dislike|love.{0,10}hate|strengths?.{0,15}weakness|good.{0,10}bad about|"
        r"best.{0,15}worst about|upsides?.{0,15}downsides?", q))
    # price only for MAGNITUDE ("how much", "$300"), not value judgements ("worth paying for")
    price_amount = bool(re.search(r"\b(how much|price point|going rate|what.*(charge|cost)|"
                                  r"\$\s?\d)\b", q))
    if flags["price"] and price_amount:
        est = "price"
    elif contrast:
        est = "contrast"
    elif ranking:
        est = "ranking"
    elif re.search(r"\b(gets? .*wrong|misconcept|myth|actually correct|popular.*(wrong|correct)|"
                   r"believe.*(true|false|correct))\b", q):
        est = "belief"
    elif re.search(r"\b(pain points?|struggl|fall short|worried|worry|frustrat|"
                   r"biggest (problem|issue|concern)|stuck|fear|anxious|anxiety)\b", q):
        est = "pain"
    elif re.search(r"\b(topics?|themes?|ideas?|use ?cases?|discuss|talk about|come up|"
                   r"aspects?|resonat|most.?talked|trending)\b", q):
        est = "topic"
    elif re.search(r"\b(opinion|sentiment|feel about|feelings|how .*view|perceiv|praise|"
                   r"reputation|likes?|love|hate)\b", q):
        est = "sentiment"
    else:
        est = "stance"
    return est, flags


_CONCEPT_STRIP = re.compile(
    r"\b(what|whats|are|is|the|a|an|top|most|best|viral|go|shareable|engaging|engagement|"
    r"resonates?|resonate|social|media|posts?|content|ideas?|make|making|about|for|to|do|"
    r"should|blog|seo|write|writing|written|search|engine|google|rank|ranking|organic|"
    r"effect|highest|related|so|that|it|on|has|have|\d+)\b", re.I)


def _concept_retrieval_query(question: str) -> str:
    """Strip concept/meta words so retrieval targets the substantive audience topics:
    'top viral topics for pre-dental social media' -> 'most discussed topics and concerns
    pre-dental' (the M1 trap was clustering the social-media-meta content instead)."""
    residual = re.sub(r"\s+", " ", _CONCEPT_STRIP.sub(" ", question.lower())).strip(" ?.")
    return f"most discussed topics and concerns {residual}".strip()


_APPLICANT_COHORTS = {"pre-dental applicant", "dental student", "sdn"}
_PRO_CUES = re.compile(r"\b(resident|omfs|oral surgeon|practic(e|ing)|professional|patient|"
                       r"associate|hygienist|clinic)\b", re.I)


def _target_cohorts(question: str) -> set | None:
    """Cohorts to retrieve from. Applicant questions scope OUT r/Dentistry patient/pro
    traffic; professional/clinical questions keep everything (None = no cohort filter)."""
    return None if _PRO_CUES.search(question or "") else _APPLICANT_COHORTS


class ResearchProtocol:
    def __init__(self, engine) -> None:
        self.e = engine
        self.cache = PositionCache(engine.base / "research_cache.sqlite")
        self._cal = CalibrationStore(engine.base / "calibration.json")
        self._criteria = ConceptCriteria(engine.base)

    # -- retrieval ----------------------------------------------------------

    def _topic_docs(self, question: str, cap: int = 4000) -> list[str]:
        sid = self.e.resolve_school(question)
        if sid:
            res = recall_and_filter(question, sid, graph_reader=self.e.reader,
                                    store=self.e.store, docs_conn=self.e.docs,
                                    link_conn=self.e.link, l1_index=self.e.l1,
                                    llm=None, display_k=25)
            return res.forum_doc_ids[:cap]
        # No-school: retrieve a larger pool, then drop junk (automod/removed) and scope to
        # the question's target cohorts (keeps r/Dentistry patient/pro traffic out of
        # applicant questions). Preserves FTS rank order.
        pool = self.e._fts_facet(question, limit=cap * 2)
        return self._clean_pool(pool, cohorts=_target_cohorts(question), cap=cap)

    def _clean_pool(self, doc_ids: list[str], *, cohorts: set | None, cap: int) -> list[str]:
        if not doc_ids:
            return []
        meta: dict[str, tuple] = {}
        for i in range(0, len(doc_ids), 400):
            batch = doc_ids[i:i + 400]
            marks = ",".join("?" * len(batch))
            for did, txt, auth, url, tid in self.e.docs.execute(
                f"SELECT doc_id, substr(text,1,200), author, url, thread_id "  # noqa: S608
                f"FROM documents WHERE doc_id IN ({marks})", batch):
                meta[did] = (txt, auth, url, tid)
        need = sorted({m[3] for d, m in meta.items() if cohorts is not None and not m[2]
                       and d.startswith("reddit_comment:") and m[3]})
        posturl: dict[str, str] = {}
        for i in range(0, len(need), 400):
            batch = need[i:i + 400]
            marks = ",".join("?" * len(batch))
            for d, u in self.e.docs.execute(
                f"SELECT doc_id, url FROM documents WHERE doc_id IN ({marks})", batch):  # noqa: S608
                if u:
                    posturl[d] = u
        out: list[str] = []
        for d in doc_ids:                       # preserve FTS rank order
            m = meta.get(d)
            if not m:
                continue
            txt, auth, url, tid = m
            if is_junk(txt, auth):
                continue
            if cohorts is not None:
                sub = subreddit_of(url) or subreddit_of(posturl.get(tid))
                ch = cohort_of(sub) if d.startswith("reddit") else "sdn"
                if ch not in cohorts:
                    continue
            out.append(d)
            if len(out) >= cap:
                break
        return out

    def _fine_topics(self, retrieval_q: str, doc_ids: list[str], *, k: int = 12) -> list[dict]:
        """Finer, balanced topic clusters via embedding k-means + batch labeling (cached)."""
        return kmeans_topics(
            self.e.store, self.e._llm, doc_ids, k=k, cache=self.cache,
            cache_key=_key(retrieval_q, f"fine{k}"),
            snippet_fn=lambda ids: _snippets(self.e.docs, ids))

    # -- bucket assignment --------------------------------------------------

    def _sentiment_buckets(self, question: str, log: list) -> tuple[dict, str, int]:
        sid = self.e.resolve_school(question)
        if sid:
            ids = [d for d in _reddit_school_set(self.e.link, self.e.reader,
                   self.e.reader.same_as_closure(sid)) if d.startswith("reddit_comment")]
            denom_desc = f"reddit comments about the school (sid={sid})"
        else:
            ids = [d for d in self._topic_docs(question) if d.startswith("reddit_comment")]
            denom_desc = "reddit comments retrieved for the topic"
        sent = self.e.reader.sentiment_for(ids)
        id_to_bucket = {d: v for v, dd in sent.items() for d in dd}
        log.append(_step("retrieve+label", f"{len(id_to_bucket)} sentiment-labelled docs; "
                         f"denominator = {denom_desc}",
                         {k: len(v) for k, v in sent.items()}))
        return id_to_bucket, denom_desc, len(ids)


    # -- shared statistical core -------------------------------------------

    def _analyze(self, question: str, est: str, id_to_bucket: dict, denom_desc: str,
                 flags: dict, log: list, *, robustness_top: float | None = None) -> dict:
        items = enrich_items(self.e.docs, id_to_bucket)
        n = len(items)
        n_threads = len({it["thread_id"] for it in items})
        n_authors = len({it["author"] for it in items if it["author"]})
        labels = sorted({it["bucket"] for it in items}, key=lambda b: -sum(
            1 for it in items if it["bucket"] == b))
        log.append(_step("denominator", f"n={n} docs in {n_threads} threads, "
                         f"{n_authors} distinct authors", {"n": n, "threads": n_threads,
                         "authors": n_authors}))

        prov = build_distribution(self.e.prov, prefix=f"{question}:{est}",
                                  buckets={lab: [it["doc_id"] for it in items
                                                 if it["bucket"] == lab] for lab in labels},
                                  source_kind="forum",
                                  method=f"{est} protocol over {denom_desc}")
        prov_by = {p.label: p for p in prov}

        buckets = []
        for lab in labels:
            k = sum(1 for it in items if it["bucket"] == lab)
            wil = stats.wilson_ci(k, n)
            cb = stats.cluster_bootstrap_ci(clusters_for(items, lab), b=1000)
            buckets.append({"label": lab, "k": k, "point": wil["point"],
                            "wilson_ci": [wil["lo"], wil["hi"]],
                            "bootstrap_ci": [cb["lo"], cb["hi"]],
                            "n_eff": cb["n_eff"], "deff": cb["deff"],
                            "stat_id": prov_by[lab].stat_id if lab in prov_by else None,
                            "drill_down": prov_by[lab].to_dict()["drill_down"] if lab in prov_by else None})
        log.append(_step("estimate+CI", "per-bucket Wilson + thread-clustered bootstrap CI; "
                         "effective N reflects within-thread echo", buckets))

        top = buckets[0] if buckets else None
        consensus = stats.consensus_index([b["point"] for b in buckets])
        measurement = None
        if top:
            # If a gold calibration exists for this estimand+class (fixed-vocab sentiment),
            # emit the Rogan-Gladen CORRECTED point + CI; else the assumed-range band.
            entry = (self._cal.get(est) or {}).get(top["label"])
            ci = top.get("bootstrap_ci")
            p_se = (ci[1] - ci[0]) / 3.92 if ci else 0.0
            if entry:
                measurement = calibrated_prevalence(top["point"], entry, p_obs_se=p_se)
            if not measurement or measurement.get("mode") != "calibrated":
                measurement = stats.rogan_gladen_band(top["point"])
                measurement["mode"] = "sensitivity_band"
        mtxt = (f"[{measurement['lo']}, {measurement['hi']}] CALIBRATED"
                if measurement and measurement.get("mode") == "calibrated"
                else f"[{measurement['corrected_lo']}, {measurement['corrected_hi']}] band"
                if measurement else "n/a")
        log.append(_step("consensus+measurement",
                         f"consensus={consensus['consensus']}; top-bucket correction -> {mtxt}",
                         {"consensus": consensus, "measurement": measurement}))

        temporal = None
        if top:
            years = sorted({it["year"] for it in items if it["year"]})
            yk = [(y, sum(1 for it in items if it["year"] == y and it["bucket"] == top["label"]),
                   sum(1 for it in items if it["year"] == y)) for y in years]
            yk = [(y, k, nn) for y, k, nn in yk if nn >= 20]
            temporal = stats.trend_test([y for y, _, _ in yk], [k for _, k, _ in yk],
                                        [nn for _, _, nn in yk])
            temporal["series"] = [{"year": y, "k": k, "n": nn, "p": round(k / nn, 3)}
                                  for y, k, nn in yk]
            log.append(_step("temporal", f"top bucket '{top['label']}' over "
                             f"{len(yk)} years: {temporal['direction']} (p={temporal.get('p')})",
                             temporal))

        cohort_split = None
        if flags.get("segment"):
            cohort_split = {}
            for ch in sorted({it["cohort"] for it in items}):
                sub = [it for it in items if it["cohort"] == ch]
                if len(sub) >= 20 and top:
                    kk = sum(1 for it in sub if it["bucket"] == top["label"])
                    cohort_split[ch] = stats.wilson_ci(kk, len(sub))
            log.append(_step("cohort", "top bucket by cohort (proxy = subreddit)", cohort_split))

        robustness = None
        if robustness_top is not None and top:
            robustness = {"baseline_top": top["point"], "perturbed_top": robustness_top,
                          "stable": abs(top["point"] - robustness_top) <= 0.05}
            log.append(_step("robustness", f"top bucket stable under threshold perturbation: "
                             f"{robustness['stable']} ({top['point']} vs {robustness_top})",
                             robustness))

        return {"denominator": {"description": denom_desc, "n": n, "n_threads": n_threads,
                                "n_authors": n_authors},
                "buckets": buckets, "consensus": consensus, "measurement": measurement,
                "temporal": temporal, "cohort_split": cohort_split, "robustness": robustness,
                "bias_label": _BIAS,
                "provenance_note": "every bucket's stat_id resolves to its exact source ids "
                                   "via GET /api/v1/dossier/sources?stat_id="}

    # -- estimand handlers --------------------------------------------------

    def _sentiment(self, question: str, flags: dict, log: list) -> dict:
        # Graph SentimentAnnotation is dense + reliable only when a school is resolved
        # (reddit_school_link + per-school annotations). For a no-school topic-sentiment
        # question, annotations cover ~7% of comments and skew to school threads, so we
        # measure opinion via the embedding stance path over the FULL retrieved set.
        if not self.e.resolve_school(question):
            log.append(_step("route", "no school -> opinion via embedding stance "
                             "(graph sentiment is school-scoped + sparse)"))
            return self._embedding_estimand(question, "stance", flags, log)
        id_to_bucket, denom, _n = self._sentiment_buckets(question, log)
        if not id_to_bucket:
            return {"answered": False, "reason": "no sentiment-labelled evidence"}
        # Graph sentiment labels are a deterministic count, so there is no threshold to
        # perturb; the relevant uncertainty is the classifier-error band (measurement).
        return {"answered": True, **self._analyze(question, "sentiment", id_to_bucket, denom,
                                                  flags, log, robustness_top=None)}

    def _embedding_estimand(self, question: str, kind: str, flags: dict, log: list) -> dict:
        doc_ids = self._topic_docs(question)
        denom = f"forum docs retrieved for the {kind} query"

        if kind in ("topic", "pain"):
            # Finer, BALANCED data-driven clusters (k-means over embeddings) instead of
            # derive-few-then-assign, which collapsed into a vague catch-all.
            dist = self._fine_topics(question, doc_ids, k=10)
            if not dist:
                return {"answered": False, "reason": "could not cluster topics"}
            id_to_bucket = {d: r["label"] for r in dist for d in r["doc_ids"]}
            log.append(_step("retrieve+label", f"k-means clustered {len(id_to_bucket)} docs "
                             f"into {len(dist)} balanced {kind} topics (finer granularity)",
                             [r["label"] for r in dist]))
            # robustness: re-cluster under a different seed; _analyze compares the top
            # cluster's share across seeds (cluster stability).
            rob = top_cluster_fraction(self.e.store, doc_ids, k=10, seed=1)
            return {"answered": True, **self._analyze(question, kind, id_to_bucket, denom,
                                                      flags, log, robustness_top=rob)}

        # stance: LLM-named viewpoints (fewer, distinct positions — not topics).
        snip = _snippets(self.e.docs, doc_ids[:40])
        snippets = [t for t in (snip.get(d, "") for d in doc_ids[:40]) if t]
        if not snippets:
            return {"answered": False, "reason": "no sample text to derive positions"}
        positions = stable_positions(self.e._llm, self.e.store, question, snippets,
                                     kind=kind, cache=self.cache)
        if not positions:
            return {"answered": False, "reason": "could not derive positions"}
        dist, *_ = classify_counted(self.e.store, positions, doc_ids, min_sim=0.12)
        id_to_bucket = {d: row["label"] for row in dist for d in row["doc_ids"]}
        if not id_to_bucket:
            return {"answered": False, "reason": "no docs classified to any bucket"}
        log.append(_step("retrieve+label", f"derived {len(positions)} stance buckets "
                         f"(cached + reproducible); classified {len(id_to_bucket)} of "
                         f"{len(doc_ids)} docs by cosine", [r["label"] for r in dist]))
        top_label = max(dist, key=lambda r: r["n"])["label"]
        dist2, *_ = classify_counted(self.e.store, positions, doc_ids, min_sim=0.20)
        tot2 = sum(r["n"] for r in dist2)
        rob = (round(next((r["n"] for r in dist2 if r["label"] == top_label), 0) / tot2, 4)
               if tot2 else None)
        return {"answered": True, **self._analyze(question, kind, id_to_bucket, denom,
                                                  flags, log, robustness_top=rob)}

    def _concept(self, question: str, concept: str, flags: dict, log: list) -> dict:
        """M3 concept-grounded hybrid: rank candidate topics by an externally-researched
        concept (e.g. virality) operationalized as weighted, normalized corpus signals.
        Surfaces demand-vs-fit divergence (most-discussed != most-shareable)."""
        spec = self._criteria.get(concept)
        log.append(_step("concept-criteria", f"concept='{concept}': {len(spec['criteria'])} "
                         f"criteria from {len(spec['sources'])} cited sources "
                         f"(researched {spec['researched_date']})",
                         {"criteria": [(c["name"], c["weight"]) for c in spec["criteria"]],
                          "sources": spec["sources"]}))
        # Intent-correct the RETRIEVAL: strip the concept/meta words ("viral", "social
        # media", "posts") so we cluster substantive audience topics, then score THOSE by
        # virality — not the social-media-meta content the raw query would pull (the M1 trap).
        retrieval_q = _concept_retrieval_query(question)
        log.append(_step("intent-correct", f"retrieval query intent-cleaned to "
                         f"'{retrieval_q}' (concept/meta words stripped)"))
        doc_ids = self._topic_docs(retrieval_q)
        dist = self._fine_topics(retrieval_q, doc_ids, k=12)
        if not dist:
            return {"answered": False, "reason": "could not cluster candidate topics"}
        log.append(_step("cluster", f"k-means clustered {len(doc_ids)} docs into {len(dist)} "
                         f"balanced topics (finer granularity)", [r["label"] for r in dist]))
        total = sum(r["n"] for r in dist) or 1
        prov = build_distribution(self.e.prov, prefix=f"{question}:concept",
                                  buckets={r["label"]: r["doc_ids"] for r in dist},
                                  source_kind="forum", method=f"{concept} concept ranking")
        pb = {p.label: p for p in prov}
        rows = []
        for r in dist:
            sig = compute_signals(self.e, r["doc_ids"])
            rows.append({"label": r["label"], "demand": r["n"],
                         "demand_pct": round(r["n"] / total, 3),
                         "stat_id": pb[r["label"]].stat_id if r["label"] in pb else None, **sig})
        keys = self._criteria.signal_keys(concept)
        rows = minmax_normalize(rows, keys)
        wmap = {c["signal"]: c["weight"] for c in spec["criteria"]}
        for r in rows:
            r["viral_fit"] = round(sum(wmap[k] * r.get(f"{k}_norm", 0.0) for k in keys), 4)
            contrib = sorted(((wmap[k] * r.get(f"{k}_norm", 0.0), k) for k in keys), reverse=True)
            r["top_drivers"] = [k for _w, k in contrib[:2]]
        rows.sort(key=lambda r: -r["viral_fit"])
        demand_rank = [r["label"] for r in sorted(rows, key=lambda r: -r["demand"])]
        log.append(_step("score+rank", f"scored {len(rows)} topics by {concept}-fit; "
                         f"fit-rank vs demand-rank divergence flagged",
                         {"fit_rank": [r["label"] for r in rows], "demand_rank": demand_rank}))
        return {"answered": True, "mode": "concept", "concept": concept,
                "criteria": spec["criteria"], "sources": spec["sources"],
                "denominator": {"description": f"candidate topics from {len(doc_ids)} "
                                f"retrieved docs", "n": len(doc_ids)},
                "ranking": rows, "demand_rank": demand_rank, "bias_label": _BIAS,
                "concept_caveat": spec["caveat"],
                "provenance_note": "each topic's stat_id resolves to its exact docs"}

    def _contrast(self, question: str, flags: dict, log: list) -> dict:
        """Compound 'praise vs criticize' — split the school's comments by sentiment, then
        topic-cluster EACH side, so the answer is the THEMES of praise vs criticism (with
        provenance), not a bare sentiment %."""
        sid = self.e.resolve_school(question)
        if not sid:
            log.append(_step("route", "no school for contrast -> stance fallback"))
            return self._embedding_estimand(question, "stance", flags, log)
        ids = [d for d in _reddit_school_set(self.e.link, self.e.reader,
               self.e.reader.same_as_closure(sid)) if d.startswith("reddit_comment")]
        sent = self.e.reader.sentiment_for(ids)
        out: dict[str, list] = {}
        for side, sideids in (("praise", sent.get("positive", [])),
                              ("criticism", sent.get("negative", []))):
            if len(sideids) < _MIN_EVIDENCE:
                out[side] = []
                continue
            snip = _snippets(self.e.docs, sideids[:40])
            snippets = [t for t in (snip.get(d, "") for d in sideids[:40]) if t]
            positions = stable_positions(self.e._llm, self.e.store, f"{question} :: {side}",
                                         snippets, kind="topic", cache=self.cache)
            dist, *_ = classify_counted(self.e.store, positions, sideids, min_sim=0.12)
            prov = build_distribution(
                self.e.prov, prefix=f"{sid}:{side}",
                buckets={r["label"]: r["doc_ids"] for r in dist},
                source_kind="reddit_comment",
                method=f"{side} themes (sentiment-conditioned topic clustering)")
            pb = {p.label: p for p in prov}
            out[side] = [{"label": r["label"], "n": r["n"], "fraction": r["fraction"],
                          "stat_id": pb[r["label"]].stat_id if r["label"] in pb else None,
                          "drill_down": (pb[r["label"]].to_dict()["drill_down"]
                                         if r["label"] in pb else None)}
                         for r in dist]
        log.append(_step("contrast", f"praise themes={len(out.get('praise', []))}, "
                         f"criticism themes={len(out.get('criticism', []))}",
                         {"n_positive": len(sent.get('positive', [])),
                          "n_negative": len(sent.get('negative', []))}))
        return {"answered": bool(out.get("praise") or out.get("criticism")),
                "mode": "contrast", "school_id": sid,
                "denominator": {"description": f"praise = {len(sent.get('positive', []))} "
                                f"positive + criticism = {len(sent.get('negative', []))} "
                                f"negative reddit comments",
                                "n_positive": len(sent.get('positive', [])),
                                "n_negative": len(sent.get('negative', []))},
                "praise": out.get("praise", []), "criticism": out.get("criticism", []),
                "bias_label": _BIAS,
                "provenance_note": "each theme's stat_id resolves to its exact comments"}

    def _ranking(self, question: str, flags: dict, log: list) -> dict:
        plan = plan_query(self.e._llm, question)
        ranked = execute_plan(plan, self.e.metrics) if plan.get("ops") else None
        if not ranked or not ranked.get("ranking"):
            return {"answered": False, "reason": "no ranking metrics available"}
        rows = ranked["ranking"]
        # shrink the per-school positive-sentiment proportion so small-n schools don't win.
        counts = [(int(round((r.get("pos_frac") or 0) * (r.get("n_comments") or 0))),
                   r.get("n_comments") or 0) for r in rows]
        shr = stats.eb_shrink(counts)
        for r, s, (k, nn) in zip(rows, shr["shrunk"], counts):
            r["pos_frac_shrunk"] = s
            r["pos_ci"] = [stats.wilson_ci(k, nn)["lo"], stats.wilson_ci(k, nn)["hi"]] if nn else None
            r["drill_down"] = f"/api/v1/dossier/sources?school={r['school_id']}&label=positive"
        log.append(_step("ranking+shrinkage", f"{len(rows)} entities; EB shrinkage prior "
                         f"mean={shr['prior_mean']} pulls small-n schools toward the center",
                         {"prior": shr}))
        return {"answered": True, "plan": plan, "ranking": rows,
                "denominator": {"description": "schools with tuition + >=50 reddit comments",
                                "n": len(rows)},
                "shrinkage": shr, "bias_label": _BIAS,
                "provenance_note": "each row drill-down recomputes the school's exact "
                                   "positive-comment ids on demand"}

    def _price(self, question: str, flags: dict, log: list) -> dict:
        doc_ids = self._topic_docs(question)
        texts = _snippets(self.e.docs, doc_ids, chars=600)
        prices: list[float] = []
        cited: list[str] = []
        for d, t in texts.items():
            ps = extract_prices(t)
            if ps:
                prices.extend(ps)
                cited.append(d)
        log.append(_step("price-extract", f"{len(prices)} dollar amounts from {len(cited)} "
                         f"of {len(doc_ids)} retrieved docs (regex proxy)",
                         {"n_prices": len(prices)}))
        if not prices:
            return {"answered": False, "reason": "no price points found in retrieved text"}
        import numpy as np
        arr = np.array(sorted(prices))
        return {"answered": True,
                "denominator": {"description": "dollar amounts in advising-context text "
                                "(proxy; reported-paid, not stated willingness)",
                                "n_prices": len(prices), "n_docs": len(cited)},
                "distribution": {"median": float(np.median(arr)),
                                 "q1": float(np.percentile(arr, 25)),
                                 "q3": float(np.percentile(arr, 75)),
                                 "min": float(arr.min()), "max": float(arr.max())},
                "sample_doc_ids": cited[:10], "bias_label": _BIAS + " Prices are amounts "
                "mentioned, not a willingness-to-pay survey; skewed by what people choose to post."}

    def run(self, question: str) -> dict:
        log: list = []
        est, flags = classify_estimand(question)
        # M3: a query invoking a researched concept (viral/shareable/engaging) over topics
        # routes to the concept-grounded hybrid path.
        concept = self._criteria.detect(question)
        if concept and (est == "topic"
                        or re.search(r"\b(topics?|posts?|content|ideas?)\b", question.lower())):
            est = "concept"
        log.append(_step("estimand", f"routed to '{est}'; modifiers={flags}"
                         + (f"; concept='{concept}'" if est == "concept" else ""), None))
        if est == "concept":
            body = self._concept(question, concept, flags, log)
        elif est == "sentiment":
            body = self._sentiment(question, flags, log)
        elif est == "contrast":
            body = self._contrast(question, flags, log)
        elif est == "ranking":
            body = self._ranking(question, flags, log)
        elif est == "price":
            body = self._price(question, flags, log)
        elif est in ("topic", "pain"):
            body = self._embedding_estimand(question, est, flags, log)
        else:                                          # stance / belief
            body = self._embedding_estimand(question, "stance", flags, log)
            body["estimand_note"] = "belief-vs-truth needs an L1 anchor; see engine.answer() " \
                "verdict for adjudication" if est == "belief" else None
        result = {"question": question, "estimand": est, "flags": flags,
                  "reasoning_log": log, **body}
        result["final_answer"] = render_research_answer(result)
        return result


def render_research_answer(d: dict) -> str:
    """Deterministic answer surface — every number is a measured estimate with its CI; the
    LLM produced none of them."""
    est = d.get("estimand")
    if not d.get("answered"):
        return f"_No defensible answer: {d.get('reason', 'insufficient evidence')}._"
    out: list[str] = []
    if est == "ranking":
        rows = d.get("ranking", [])
        out.append("**Ranking** (tuition = official L1; positive sentiment EB-shrunk, "
                   "with 95% CI):\n")
        out.append("| # | School | Tuition | Positive (shrunk) | 95% CI | Comments |")
        out.append("|--:|--------|--------:|------------------:|:------:|---------:|")
        for i, r in enumerate(rows[:15], 1):
            t = f"${r['tuition']:,.0f}" if r.get("tuition") else "—"
            ci = (f"{r['pos_ci'][0]*100:.0f}–{r['pos_ci'][1]*100:.0f}%"
                  if r.get("pos_ci") else "—")
            out.append(f"| {i} | {(r.get('name') or '').title()} | {t} | "
                       f"{(r.get('pos_frac_shrunk') or 0)*100:.0f}% | {ci} | "
                       f"{r.get('n_comments', 0):,} |")
    elif est == "concept":
        out.append(f"**{d['concept'].title()}-fit ranking** of topics — criteria from "
                   f"{len(d.get('sources', []))} cited sources, scored on proxy corpus signals "
                   f"(not platform metrics):\n")
        out.append("| Rank | Topic | Fit | Demand | Top drivers |")
        out.append("|--:|--|--:|--:|--|")
        for i, r in enumerate(d.get("ranking", [])[:10], 1):
            out.append(f"| {i} | {r['label']} | {r['viral_fit']:.2f} | {r['demand']:,} "
                       f"({r['demand_pct'] * 100:.0f}%) | {', '.join(r.get('top_drivers', []))} |")
        if d.get("demand_rank"):
            out.append(f"\n_Demand rank (for contrast): {' > '.join(d['demand_rank'][:5])}_")
        out.append(f"\n_{d.get('concept_caveat', '')}_")
    elif est == "contrast":
        den = d.get("denominator", {})
        out.append(f"**Praise vs criticism** (themes within {den.get('n_positive', 0):,} "
                   f"positive and {den.get('n_negative', 0):,} negative comments):\n")
        for side in ("praise", "criticism"):
            rows = d.get(side, [])
            out.append(f"_{side.title()}:_")
            for r in rows[:5]:
                out.append(f"- {r['label']} — {r['fraction'] * 100:.0f}% ({r['n']:,})")
            out.append("")
    elif est == "price":
        dist, den = d["distribution"], d["denominator"]
        out.append(f"**Price points (proxy, n={den['n_prices']} amounts in {den['n_docs']} "
                   f"docs):** median **${dist['median']:,.0f}**, IQR "
                   f"${dist['q1']:,.0f}–${dist['q3']:,.0f} (range ${dist['min']:,.0f}–"
                   f"${dist['max']:,.0f}).")
    else:
        den = d["denominator"]
        out.append(f"**Estimate** · n={den['n']} docs / {den['n_threads']} threads / "
                   f"{den['n_authors']} authors:")
        for b in d.get("buckets", [])[:5]:
            out.append(f"- **{b['label']}**: {b['point']*100:.0f}% "
                       f"(95% CI {b['bootstrap_ci'][0]*100:.0f}–{b['bootstrap_ci'][1]*100:.0f}%, "
                       f"n_eff={b['n_eff']:.0f}, k={b['k']})")
        c = d.get("consensus") or {}
        out.append(f"\nConsensus {c.get('consensus')} (top margin "
                   f"{(c.get('margin') or 0)*100:.0f}pts).")
        m = d.get("measurement") or {}
        if m.get("mode") == "calibrated" and m.get("reliable"):
            out.append(f"**Calibrated** top-bucket prevalence: {m['point']*100:.0f}% "
                       f"(95% CI {m['lo']*100:.0f}–{m['hi']*100:.0f}%; sens={m['sens']}, "
                       f"spec={m['spec']}, n_gold={m['n_gold']}; silver reference, not human gold).")
        elif m.get("mode") == "calibrated":
            out.append(f"⚠ Calibration flag: the classifier is too noisy to correct this "
                       f"bucket reliably (Youden J={m['youden']}, sens={m['sens']}) — corrected "
                       f"rate poorly identified (CI {m['lo']*100:.0f}–{m['hi']*100:.0f}%). "
                       f"Treat the observed % as indicative, not precise.")
        elif m:
            out.append(f"Classifier-error band on the top bucket: "
                       f"{m['corrected_lo']*100:.0f}–{m['corrected_hi']*100:.0f}% "
                       f"(sensitivity analysis; not gold-calibrated).")
        t = d.get("temporal") or {}
        if t.get("direction") and t["direction"] not in ("insufficient_years", "degenerate"):
            extra = (f", slope {t['slope_per_year']}/yr, p={t['p']}"
                     if t.get("slope_per_year") is not None else "")
            out.append(f"Temporal (top bucket): **{t['direction']}**{extra}.")
        rob = d.get("robustness") or {}
        if rob:
            out.append(f"Robustness: top bucket {'stable' if rob['stable'] else 'UNSTABLE'} "
                       f"under perturbation ({rob['baseline_top']} vs {rob['perturbed_top']}).")
        cs = d.get("cohort_split")
        if cs:
            out.append("By cohort: " + "; ".join(
                f"{k} {v['point']*100:.0f}% (n={v['n']})" for k, v in cs.items()))
    out.append(f"\n_{d.get('bias_label', '')}_")
    out.append(f"_{d.get('provenance_note', '')}_")
    return "\n".join(out)
