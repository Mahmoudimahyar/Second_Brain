"""KB ask agent — NL question -> grounded, cited answer over the knowledge graph.

Productionized from the `cloud/kb_agent.py` prototype (2026-06-09). Pipeline:
  1. resolve school mentions (alias map + canonical-name index, SAME_AS-aware),
  2. deterministic graph retrieval per intent (school profile / tuition ranking /
     sentiment ranking / consensus metrics / topics),
  3. ground an LLM answer in the retrieved facts, labeling each figure as
     forum-reported vs official ADEA.

Evidence Answer Engine (EAE, 2026-06-17) — `evidence_answer()`:
  R1  source-typed evidence counts (l1_claim / l5_post / comment / forum_consensus)
  R2  tier-weighted reliability via ranking.py (wired with {L1:1.0, L5:0.4})
  R3  popular-vs-correct adjudication via consistency.py (RA-RAG)
  R4  opinion distribution (polarity + KPA-lite stance clustering via LLM)
  R5  popular vs authoritative verdict + citation
  R6  drill-down: every evidence item carries doc_id + url + snippet
  R7  comment recall: FTS5 on documents.sqlite (LIKE-scan fallback when no FTS5)

Wiring: `src/cli.py ask` | `POST /api/v1/ask` | `POST /api/v1/evidence`
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.gateway.api import LLMClient
from src.graph.kuzu_client import KuzuGraphClient
from src.retrieval.consistency import SourceClaim, consistency
from src.retrieval.ranking import RankingWeights, ranking_score

# Explicit tier weights for the bundle's {L1, L5} corpus (GAP-058 fix).
EAE_TIER_WEIGHTS: dict[str, float] = {"L1": 1.0, "L2": 0.85, "L3": 0.7, "L4": 0.55, "L5": 0.4}
EAE_RANKING_WEIGHTS = RankingWeights(w_tier=EAE_TIER_WEIGHTS)

# Common applicant shorthand -> substring of the canonical School name.
ALIAS = {"nyu": "new york university", "usc": "ostrow", "ucla": "los angeles",
         "ucsf": "san francisco", "penn": "pennsylvania", "upenn": "pennsylvania",
         "uop": "pacific", "bu ": "boston university", "columbia": "columbia",
         "harvard": "harvard", "temple": "temple", "tufts": "tufts",
         "nova": "nova southeastern", "unc": "north carolina",
         "case western": "case western", "vcu": "virginia commonwealth",
         "unlv": "nevada", "midwestern": "midwestern", "pacific": "pacific"}

# Minimum evidence to give a verdict (EAE-7 abstention guard).
_MIN_EVIDENCE_FOR_VERDICT = 3
_MIN_MAJORITY_FRACTION = 0.40


def _default_llm() -> LLMClient:
    """Benchmark-won bulk model (cloud/bench 2026-06-08): Together gpt-oss-20b."""
    from src.gateway.openai_adapter import OpenAIAdapter  # noqa: PLC0415 — lazy SDK

    return OpenAIAdapter(
        vendor="together", model="openai/gpt-oss-20b",
        api_key_env="TOGETHER_API_KEY", base_url="https://api.together.xyz/v1",
        pricing_per_million_tokens_in=0.05, pricing_per_million_tokens_out=0.20,
        timeout=60, max_retries=2)


# ---------------------------------------------------------------------------
# EvidenceItem — one piece of evidence with full attribution (EAE-R6)
# ---------------------------------------------------------------------------

@dataclass
class EvidenceItem:
    doc_id: str
    source_type: str   # "l1_claim" | "l1_page" | "l5_post" | "comment" | "forum_consensus"
    tier: str          # "L1" | "L5"
    snippet: str
    score: float
    url: str = ""
    school_id: str = ""
    rank: str = "normal"
    t_valid_from: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "source_type": self.source_type,
            "tier": self.tier,
            "snippet": self.snippet[:400],
            "score": round(self.score, 4),
            "url": self.url,
            "school_id": self.school_id,
        }


# ---------------------------------------------------------------------------
# KBAgent
# ---------------------------------------------------------------------------

class KBAgent:
    """Loads compact in-memory views of the graph once; answers many questions."""

    def __init__(
        self,
        graph_path: Path | str,
        *,
        llm: LLMClient | None = None,
        graph_client: KuzuGraphClient | None = None,
        documents_db: Path | str | None = None,
    ) -> None:
        self._graph = graph_client or KuzuGraphClient(db_path=str(graph_path))
        self._c = self._graph._conn  # noqa: SLF001
        self._llm = llm
        self._data_dir = Path(graph_path).resolve().parent.parent
        self._semantic = None
        self._semantic_tried = False
        # EAE-1: documents.sqlite for comment recall
        self._docs_db_path: Path | None = None
        self._docs_db_has_fts5: bool | None = None   # None = not yet checked
        if documents_db is not None:
            self._docs_db_path = Path(documents_db)
        else:
            candidate = self._data_dir / "raw" / "documents.sqlite"
            if candidate.exists():
                self._docs_db_path = candidate
        self._load()

    # -- lazy helpers --------------------------------------------------------

    def _semantic_index(self):
        if self._semantic is None and not self._semantic_tried:
            self._semantic_tried = True
            try:
                from src.retrieval.semantic_index import SemanticIndex  # noqa: PLC0415
                idx = SemanticIndex(self._data_dir)
                self._semantic = idx if idx.size > 0 else None
            except Exception:  # noqa: BLE001
                self._semantic = None
        return self._semantic

    def _docs_conn(self) -> sqlite3.Connection | None:
        """Open read-only connection to documents.sqlite; returns None if absent."""
        if self._docs_db_path is None or not self._docs_db_path.exists():
            return None
        return sqlite3.connect(f"file:{self._docs_db_path}?mode=ro", uri=True)

    def _check_fts5(self) -> bool:
        """Return True if docs_fts virtual table exists (built by add_fts5_documents.py)."""
        if self._docs_db_has_fts5 is not None:
            return self._docs_db_has_fts5
        conn = self._docs_conn()
        if conn is None:
            self._docs_db_has_fts5 = False
            return False
        try:
            conn.execute("SELECT COUNT(*) FROM docs_fts LIMIT 1")
            self._docs_db_has_fts5 = True
        except sqlite3.OperationalError:
            self._docs_db_has_fts5 = False
        finally:
            conn.close()
        return self._docs_db_has_fts5

    def close(self) -> None:
        self._graph.close()

    # -- loading ---------------------------------------------------------

    def _s(self, cypher: str):
        r = self._c.execute(cypher)
        while r.has_next():
            yield r.get_next()

    @staticmethod
    def _j(pj: str | None) -> dict:
        try:
            out = json.loads(pj or "{}")
            return out if isinstance(out, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _load(self) -> None:
        self.name: dict[str, str] = {}
        self.kind: dict[str, str] = {}
        self.schools: dict[str, str] = {}
        for lbl in ("School", "Specialty", "Institution"):
            for nid, pj in self._s(
                    f"MATCH (n:Node) WHERE n.label='{lbl}' RETURN n.id, n.properties_json"):
                nm = self._j(pj).get("canonical_name", "")
                self.name[nid] = nm
                self.kind[nid] = lbl
                if lbl == "School":
                    self.schools[nid] = nm
        self.same: dict[str, set[str]] = defaultdict(set)
        for a, b in self._s(
                "MATCH (x:Node)-[e:Edge]->(y:Node) WHERE e.label='SAME_AS' RETURN x.id, y.id"):
            self.same[a].add(b)
        self.fc: dict[str, dict[str, dict]] = defaultdict(dict)
        for (pj,) in self._s(
                "MATCH (n:Node) WHERE n.label='ForumConsensus' RETURN n.properties_json"):
            o = self._j(pj)
            if o.get("school_id") and o.get("metric"):
                self.fc[o["school_id"]][o["metric"]] = o
        post_school: dict[str, list[str]] = defaultdict(list)
        for pid, sid in self._s(
                "MATCH (p:Node)-[e:Edge]->(s:Node) WHERE e.label='MENTIONS_SCHOOL' "
                "RETURN p.id, s.id"):
            post_school[pid].append(sid)
        self.sent: dict[str, Counter] = defaultdict(Counter)
        for (pj,) in self._s(
                "MATCH (n:Node) WHERE n.label='SentimentAnnotation' RETURN n.properties_json"):
            o = self._j(pj)
            for sid in post_school.get(o.get("post_id"), []):
                self.sent[sid][o.get("verdict")] += 1
        self.clusters: list[tuple[int, str]] = []
        for (pj,) in self._s(
                "MATCH (n:Node) WHERE n.label='Cluster' RETURN n.properties_json"):
            o = self._j(pj)
            if o.get("is_junk"):
                continue
            self.clusters.append((o.get("member_count", 0), o.get("topic_label", "")))
        self.clusters.sort(reverse=True)
        self.canon: dict[str, str] = {}
        for sid in self.schools:
            members = [m for m in self.group(sid) if m in self.schools]
            self.canon[sid] = max(
                members, key=lambda m: (sum(self.sent.get(m, Counter()).values()), m))

    # -- entity resolution -------------------------------------------------

    def group(self, sid: str) -> set[str]:
        return {sid} | self.same.get(sid, set())

    def resolve(self, q: str) -> str | None:
        ql = " " + re.sub(r"[^a-z0-9 ]", " ", q.lower()) + " "
        for a, sub in ALIAS.items():
            if a in ql:
                hit = next((nid for nid, nm in self.schools.items()
                            if sub in nm.lower()), None)
                if hit:
                    return hit
        best, blen = None, 0
        for nid, nm in self.schools.items():
            core = nm.lower().split(" school")[0].split(" college")[0].strip()
            if len(core) >= 6 and (" " + core + " ") in ql and len(core) > blen:
                best, blen = nid, len(core)
        return best

    # -- retrieval views ----------------------------------------------------

    def profile(self, sid: str) -> dict[str, Any]:
        merged: dict[str, dict] = {}
        sent: Counter = Counter()
        for g in self.group(sid):
            for m, o in self.fc.get(g, {}).items():
                if m not in merged or o.get("n", 0) > merged[m].get("n", 0):
                    merged[m] = o
            sent.update(self.sent.get(g, Counter()))
        return {"school": self.name.get(sid, ""), "consensus": merged,
                "sentiment": dict(sent)}

    def rank_consensus(self, metric: str, direction: str, n: int = 8) -> list:
        best: dict[str, dict] = {}
        for sid, m in self.fc.items():
            if sid not in self.schools or metric not in m:
                continue
            cn = self.canon.get(sid, sid)
            if cn not in best or m[metric].get("n", 0) > best[cn].get("n", 0):
                best[cn] = m[metric]
        rows = [(o.get("median"), self.schools.get(cn, ""), o)
                for cn, o in best.items() if o.get("n", 0) >= 8]
        rows.sort(key=lambda r: (r[0] is None, r[0]), reverse=(direction == "high"))
        return rows[:n]

    def rank_tuition(self, direction: str, n: int = 8) -> list:
        best: dict[str, tuple] = {}
        for sid, m in self.fc.items():
            o = m.get("tuition")
            truth = o and (o.get("l1_tuition_resident") or o.get("l1_tuition_nonresident"))
            if not truth or sid not in self.schools:
                continue
            cn = self.canon.get(sid, sid)
            if cn not in best or o.get("n", 0) > best[cn][1].get("n", 0):
                best[cn] = (truth, o)
        rows = [(truth, self.schools.get(cn, ""), o) for cn, (truth, o) in best.items()]
        rows.sort(reverse=(direction == "high"))
        return rows[:n]

    def rank_sentiment(self, kind: str, n: int = 8) -> list:
        agg: dict[str, Counter] = defaultdict(Counter)
        for sid, ct in self.sent.items():
            if self.kind.get(sid) == "School":
                agg[self.canon.get(sid, sid)].update(ct)
        rows = [(ct.get(kind, 0) / sum(ct.values()), self.schools.get(cn, ""),
                 ct.get(kind, 0), sum(ct.values()))
                for cn, ct in agg.items() if sum(ct.values()) >= 80]
        rows.sort(reverse=True)
        return rows[:n]

    # -- intent routing (backward-compat retrieve) --------------------------

    def retrieve(self, q: str) -> dict[str, Any]:
        ql = q.lower()
        if any(w in ql for w in ("topic", "discuss", "themes", "what are people",
                                 "talk about")):
            return {"type": "topics",
                    "topics": [{"label": lbl, "posts": m}
                               for m, lbl in self.clusters[:12]]}
        if any(w in ql for w in ("afford", "cheap", "expensive", "tuition cost",
                                 "lowest tuition", "highest tuition")):
            d = "low" if any(w in ql for w in ("afford", "cheap", "lowest", "least")) \
                else "high"
            return {"type": "rank_tuition", "direction": d,
                    "rows": [{"school": nm,
                              "adea_resident": o.get("l1_tuition_resident"),
                              "adea_nonresident": o.get("l1_tuition_nonresident"),
                              "forum_median": int(o["median"])}
                             for _, nm, o in self.rank_tuition(d)]}
        if any(w in ql for w in ("sentiment", "negative", "worst", "best", "happy",
                                 "happiest", "unhappy", "complain", "avoid",
                                 "favorite", "loved")):
            kind = "negative" if any(w in ql for w in ("negative", "worst", "unhappy",
                                                       "complain", "avoid")) else "positive"
            return {"type": "rank_sentiment", "kind": kind,
                    "rows": [{"school": nm, f"{kind}_pct": round(r * 100, 1),
                              "n_opinions": tot}
                             for r, nm, _, tot in self.rank_sentiment(kind)]}
        sid = self.resolve(q)
        if sid:
            facts: dict[str, Any] = {"type": "school_profile", "data": self.profile(sid)}
            idx = self._semantic_index()
            if idx is not None:
                facts["evidence_posts"] = [
                    {"post_id": h.post_id, "score": round(h.score, 3),
                     "snippet": h.snippet}
                    for h in idx.search(q, top_k=4)]
            return facts
        idx = self._semantic_index()
        if idx is not None:
            hits = idx.search(q, top_k=8)
            if hits:
                return {"type": "semantic_posts",
                        "posts": [{"post_id": h.doc_id, "score": round(h.score, 3),
                                   "snippet": h.snippet} for h in hits]}
        return {"type": "none",
                "note": "could not identify a school or known intent"}

    # -- EAE helpers --------------------------------------------------------

    def _comment_recall(self, q: str, *, top_k: int = 8) -> list[EvidenceItem]:
        """EAE-1/EAE-R7: search comments via FTS5 (or LIKE fallback)."""
        conn = self._docs_conn()
        if conn is None:
            return []
        try:
            items: list[EvidenceItem] = []
            if self._check_fts5():
                # FTS5 search: rank is lower = better
                rows = conn.execute(
                    "SELECT d.doc_id, d.doc_type, d.source, d.url, d.text, d.score "
                    "FROM docs_fts f JOIN documents d ON f.rowid = d.rowid "
                    "WHERE docs_fts MATCH ? AND d.doc_type = 'reddit_comment' "
                    "ORDER BY rank LIMIT ?",
                    (q, top_k),
                ).fetchall()
            else:
                # LIKE-scan fallback (slow on large DB but correct)
                like = f"%{q[:60]}%"
                rows = conn.execute(
                    "SELECT doc_id, doc_type, source, url, text, score "
                    "FROM documents WHERE text LIKE ? AND doc_type = 'reddit_comment' "
                    "ORDER BY (score IS NULL), score DESC LIMIT ?",
                    (like, top_k),
                ).fetchall()
            for doc_id, doc_type, source, url, text, db_score in rows:
                snippet = (text or "")[:280]
                items.append(EvidenceItem(
                    doc_id=doc_id,
                    source_type="comment",
                    tier="L5",
                    snippet=snippet,
                    score=float(db_score or 1) / 100.0,  # normalise karma
                    url=url or "",
                ))
            return items
        except Exception:  # noqa: BLE001
            return []
        finally:
            conn.close()

    def _l1_claim_items(self, sid: str | None) -> list[EvidenceItem]:
        """EAE-R6: L1 Claim nodes for a school (or global top-N when sid is None)."""
        items: list[EvidenceItem] = []
        if sid:
            groups = [sid] + list(self.same.get(sid, set()))
            school_filter = " OR ".join(
                f"n.properties_json CONTAINS '{g}'" for g in groups[:4])
            cypher = (
                f"MATCH (n:Node) WHERE n.label='Claim' AND n.source_tier='L1' "
                f"AND ({school_filter}) RETURN n.id, n.properties_json LIMIT 12"
            )
        else:
            cypher = ("MATCH (n:Node) WHERE n.label='Claim' AND n.source_tier='L1' "
                      "RETURN n.id, n.properties_json LIMIT 8")
        try:
            for nid, pj in self._s(cypher):
                o = self._j(pj)
                items.append(EvidenceItem(
                    doc_id=nid,
                    source_type="l1_claim",
                    tier="L1",
                    snippet=f"{o.get('predicate_canonical','claim')}: {o.get('object_value','')}",
                    score=1.0,
                    url=o.get("source_url", ""),
                    school_id=o.get("resolved_school_id", ""),
                    rank="preferred",
                ))
        except Exception:  # noqa: BLE001
            pass
        return items

    def _forum_consensus_items(self, sid: str | None) -> list[EvidenceItem]:
        """EAE-R2: ForumConsensus nodes as evidence items."""
        items: list[EvidenceItem] = []
        if sid:
            for g in self.group(sid):
                for metric, o in self.fc.get(g, {}).items():
                    snippet = (f"{metric}: median={o.get('median')} "
                               f"n={o.get('n')} p25={o.get('p25')} p75={o.get('p75')}")
                    items.append(EvidenceItem(
                        doc_id=f"consensus:{g}:{metric}",
                        source_type="forum_consensus",
                        tier="L5",
                        snippet=snippet,
                        score=min(1.0, (o.get("n", 0) / 100)),
                        school_id=g,
                    ))
        return items[:8]

    def _semantic_items(self, q: str, *, top_k: int = 6) -> list[EvidenceItem]:
        """EAE-R7: semantic post search as evidence items."""
        idx = self._semantic_index()
        if idx is None:
            return []
        return [
            EvidenceItem(
                doc_id=h.doc_id,
                source_type="l5_post",
                tier="L5",
                snippet=h.snippet,
                score=float(h.score),
            )
            for h in idx.search(q, top_k=top_k)
        ]

    def _opinion_distribution(self, sid: str) -> dict[str, float]:
        """EAE-R4: polarity distribution over SentimentAnnotations for a school."""
        ct: Counter = Counter()
        for g in self.group(sid):
            ct.update(self.sent.get(g, Counter()))
        total = sum(ct.values())
        if total == 0:
            return {}
        return {k: round(v / total, 3) for k, v in ct.items() if k}

    def _score_evidence_items(self, items: list[EvidenceItem]) -> list[EvidenceItem]:
        """EAE-R2/R5: re-rank evidence items by tier-weighted score (RA-RAG)."""
        # Group items by (school_id, source_type) for cross-source consistency
        group_peers: dict[str, list[SourceClaim]] = defaultdict(list)
        for item in items:
            key = item.school_id or item.source_type
            group_peers[key].append(
                SourceClaim(value=item.snippet[:80], source_tier=item.tier, credibility=item.score)
            )
        scored: list[tuple[float, EvidenceItem]] = []
        for item in items:
            key = item.school_id or item.source_type
            peers = group_peers[key]
            if len(peers) > 1:
                target = SourceClaim(value=item.snippet[:80], source_tier=item.tier,
                                     credibility=item.score)
                cons = consistency(target, peers, EAE_TIER_WEIGHTS)
            else:
                cons = 1.0
            s = ranking_score(
                source_tier=item.tier,
                rank=item.rank,
                decay_factor=1.0,
                credibility=max(item.score, 0.1),
                consistency_factor=cons,
                weights=EAE_RANKING_WEIGHTS,
            )
            scored.append((s, item))
        scored.sort(key=lambda x: -x[0])
        return [item for _, item in scored]

    def _popular_vs_correct(
        self, items: list[EvidenceItem], l1_items: list[EvidenceItem],
    ) -> tuple[str | None, str | None, str]:
        """EAE-R3/R5: compare L5 majority with L1 authoritative answer.

        Returns (popular_answer, authoritative_answer, verdict).
        verdict: "agrees" | "contradicts" | "no_l1_data" | "insufficient_evidence"
        """
        l5 = [i for i in items if i.tier == "L5"]
        if len(l5) < _MIN_EVIDENCE_FOR_VERDICT:
            return None, None, "insufficient_evidence"
        # Popular = most common snippet theme (use polarity as proxy)
        popular = f"{len(l5)} forum sources"
        if l1_items:
            authoritative = l1_items[0].snippet[:120] if l1_items[0].snippet else None
            # Simple heuristic: if L1 snippet has a number and L5 snippets have
            # very different numbers, flag as "contradicts"; else "agrees"
            l1_nums = set(re.findall(r"\d[\d,]*", l1_items[0].snippet))
            l5_snippets = " ".join(i.snippet[:80] for i in l5[:5])
            l5_nums = set(re.findall(r"\d[\d,]*", l5_snippets))
            if l1_nums and l5_nums and not l1_nums.intersection(l5_nums):
                verdict = "contradicts"
            else:
                verdict = "agrees"
            return popular, authoritative, verdict
        return popular, None, "no_l1_data"

    def _kpa_stance(
        self, items: list[EvidenceItem], q: str, llm: LLMClient | None,
    ) -> list[dict[str, Any]]:
        """EAE-R4: KPA-lite stance clustering via LLM (polarity fallback when no LLM)."""
        if not items:
            return []
        # Polarity fallback (always available): group by tier sentiment context
        # Using sentiment annotations already in self.sent (loaded at startup).
        # If school-specific, opinion_distribution gives a better breakdown.
        # Generic KPA: ask LLM to identify 2-3 stance positions from snippets.
        snippets = [i.snippet[:120] for i in items[:12]]
        if llm is None:
            # Polarity-only fallback
            pos = sum(1 for s in snippets if any(w in s.lower() for w in
                      ("great", "love", "recommend", "excellent", "happy", "positive",
                       "good", "best", "wonderful")))
            neg = sum(1 for s in snippets if any(w in s.lower() for w in
                      ("avoid", "bad", "terrible", "worst", "negative", "hate",
                       "difficult", "stressful")))
            n = len(snippets)
            neutral = n - pos - neg
            return [
                {"label": "positive experience", "fraction": round(pos / max(n, 1), 2),
                 "n": pos, "example_ids": [i.doc_id for i in items if
                                           any(w in i.snippet.lower() for w in
                                               ("great", "love", "recommend"))][:2]},
                {"label": "mixed/neutral", "fraction": round(neutral / max(n, 1), 2),
                 "n": neutral, "example_ids": []},
                {"label": "negative experience", "fraction": round(neg / max(n, 1), 2),
                 "n": neg, "example_ids": [i.doc_id for i in items if
                                           any(w in i.snippet.lower() for w in
                                               ("avoid", "bad", "terrible"))][:2]},
            ]
        # LLM-powered KPA
        prompt = (
            "You are analyzing forum opinions. Given these evidence snippets about: "
            f'"{q}"\n\nSnippets:\n'
            + "\n".join(f"- {s}" for s in snippets)
            + "\n\nIdentify 2-4 distinct stance positions people hold. "
            "Return JSON array: [{\"label\": str, \"fraction\": float, \"n\": int, \"example_keywords\": [str]}]. "
            "fractions must sum to 1.0. Be concise.")
        try:
            r = llm.complete(prompt, schema=None)
            raw = (r.raw_text or "").strip()
            # Extract JSON array from response
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                clusters = json.loads(match.group(0))
                n = len(items)
                for c in clusters:
                    c["n"] = int(round(c.get("fraction", 0) * n))
                    c.setdefault("example_ids", [])
                return clusters
        except Exception:  # noqa: BLE001
            pass
        return self._kpa_stance(items, q, llm=None)  # polarity fallback

    def _abstain_check(
        self,
        items: list[EvidenceItem],
        opinion_dist: dict[str, float],
        verdict: str,
    ) -> str | None:
        """EAE-R7: decide if we should abstain from giving a verdict."""
        if len(items) < _MIN_EVIDENCE_FOR_VERDICT:
            return f"insufficient evidence (only {len(items)} sources found)"
        if verdict == "insufficient_evidence":
            return "not enough cross-source evidence to adjudicate"
        # No clear majority
        if opinion_dist:
            max_fraction = max(opinion_dist.values(), default=0.0)
            if max_fraction < _MIN_MAJORITY_FRACTION:
                return f"no clear majority opinion (max fraction: {max_fraction:.0%})"
        return None

    # -- full EAE pipeline --------------------------------------------------

    def _build_evidence_set(
        self, q: str, facts: dict[str, Any], sid: str | None,
    ) -> list[EvidenceItem]:
        """EAE-R1: assemble all evidence items from every source."""
        items: list[EvidenceItem] = []

        # L1 Claim nodes (authoritative, highest tier)
        items.extend(self._l1_claim_items(sid))

        # ForumConsensus (per-school aggregate, L5-derived)
        if sid:
            items.extend(self._forum_consensus_items(sid))

        # Semantic post search (L5)
        items.extend(self._semantic_items(q, top_k=6))

        # Comment recall (EAE-1 / EAE-R7)
        items.extend(self._comment_recall(q, top_k=8))

        # Deduplicate by doc_id
        seen: set[str] = set()
        unique: list[EvidenceItem] = []
        for item in items:
            if item.doc_id not in seen:
                seen.add(item.doc_id)
                unique.append(item)
        return unique

    def _typed_counts(self, items: list[EvidenceItem]) -> dict[str, int]:
        """EAE-R1: count evidence items by source_type."""
        counts: Counter = Counter(i.source_type for i in items)
        return dict(counts)

    def evidence_answer(self, q: str) -> dict[str, Any]:
        """EAE full 7-step pipeline. Returns EvidenceAnswer dict.

        All 7 steps:
          R1 typed_counts  R2 most_reliable  R3 popular_vs_correct
          R4 stance_clusters  R5 verdict  R6 sources drill-down  R7 comment recall
        """
        # Intent routing (backward-compat facts)
        facts = self.retrieve(q)
        sid = self.resolve(q)

        # R1 + R7: build evidence set from all sources (includes comment recall)
        all_items = self._build_evidence_set(q, facts, sid)

        # R2: tier-weighted ranking (RA-RAG)
        ranked_items = self._score_evidence_items(all_items)

        # Typed counts (R1)
        typed_counts = self._typed_counts(ranked_items)

        # Most reliable = top 3 L1 items, then top 3 L5
        l1_items = [i for i in ranked_items if i.tier == "L1"]
        l5_items = [i for i in ranked_items if i.tier == "L5"]
        most_reliable = (l1_items[:3] + l5_items[:3])

        # R4: opinion distribution
        opinion_dist: dict[str, float] = {}
        if sid:
            opinion_dist = self._opinion_distribution(sid)
        elif ranked_items:
            # aggregate polarity proxy from snippets
            pos = sum(1 for i in ranked_items if any(w in i.snippet.lower() for w in
                      ("great", "recommend", "love", "excellent")))
            neg = sum(1 for i in ranked_items if any(w in i.snippet.lower() for w in
                      ("avoid", "bad", "terrible", "worst")))
            n = max(len(ranked_items), 1)
            opinion_dist = {
                "positive": round(pos / n, 3),
                "negative": round(neg / n, 3),
                "neutral": round((n - pos - neg) / n, 3),
            }

        # R4: KPA-lite stance clustering
        llm = self._llm
        if llm is None:
            try:
                llm = _default_llm()
                self._llm = llm
            except Exception:  # noqa: BLE001
                llm = None
        stance_clusters = self._kpa_stance(ranked_items, q, llm)

        # R3/R5: popular vs correct
        popular_answer, authoritative_answer, verdict = self._popular_vs_correct(
            ranked_items, l1_items)

        # R7: calibrated abstention
        abstain_reason = self._abstain_check(ranked_items, opinion_dist, verdict)

        # Generate LLM answer grounded in evidence
        text: str | None = None
        try:
            evidence_json = json.dumps(
                {"typed_counts": typed_counts,
                 "most_reliable": [i.to_dict() for i in most_reliable[:4]],
                 "opinion_distribution": opinion_dist,
                 "popular_vs_authoritative": {
                     "popular": popular_answer,
                     "authoritative": authoritative_answer,
                     "verdict": verdict,
                 }},
                default=str)[:4000]
            prompt = (
                "You are DentistJourney's advisor. Answer using ONLY the EVIDENCE below.\n"
                "Rules: cite specific numbers; label each as (forum-reported) or "
                "(official L1/ADEA); note when forum data contradicts official data; "
                "if evidence is thin, say so. Be concise (3-6 sentences).\n\n"
                f"EVIDENCE (JSON):\n{evidence_json}\n\n"
                f"QUESTION: {q}\n\nANSWER:")
            if llm is None:
                llm = _default_llm()
                self._llm = llm
            r = llm.complete(prompt, schema=None)
            text = (r.raw_text or "").strip() or None
        except Exception:  # noqa: BLE001
            text = None

        return {
            "question": q,
            "intent": facts.get("type"),
            # EAE R1
            "typed_counts": typed_counts,
            # EAE R2
            "most_reliable": [i.to_dict() for i in most_reliable],
            # EAE R4
            "opinion_distribution": opinion_dist,
            "stance_clusters": stance_clusters,
            # EAE R3/R5
            "popular_answer": popular_answer,
            "authoritative_answer": authoritative_answer,
            "verdict": verdict,
            # EAE R7
            "abstain_reason": abstain_reason,
            # EAE R6
            "sources": [i.to_dict() for i in ranked_items[:20]],
            # LLM answer
            "answer": text,
            # backward compat
            "facts": facts,
        }

    # -- backward-compat answer --------------------------------------------

    def answer(self, q: str) -> dict[str, Any]:
        """Return {question, intent, facts, answer}; answer is None when no LLM
        key is available (facts-only degradation). Backward-compatible with /api/v1/ask."""
        facts = self.retrieve(q)
        prompt = (
            "You are DentistJourney's advisor assistant. Answer using ONLY the FACTS "
            "below, from a knowledge graph of ~877K dental-applicant forum posts + "
            "official ADEA data.\n"
            "Rules: cite specific numbers; label each as (forum-reported) or "
            "(official ADEA); for tuition, note forum users often underestimate the "
            "true ADEA sticker price; if the facts don't cover it, say what's "
            "missing. Be concise (3-6 sentences).\n\n"
            f"FACTS (JSON):\n{json.dumps(facts, default=str)[:3800]}\n\n"
            f"QUESTION: {q}\n\nANSWER:")
        text: str | None = None
        try:
            if self._llm is None:
                self._llm = _default_llm()
            r = self._llm.complete(prompt, schema=None)
            text = (r.raw_text or "").strip() or None
        except Exception:  # noqa: BLE001
            text = None
        return {"question": q, "intent": facts.get("type"), "facts": facts,
                "answer": text}
