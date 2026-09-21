"""PV-4: compositional query planner.

A single-intent router answered "cheapest schools that applicants also like" with
tuition only and let the LLM fabricate the "applicants like" half (#35). Instead, an
LLM planner emits a TYPED plan over a fixed op vocabulary, and the plan is executed
deterministically over the precomputed `school_metrics` table (built by
`cloud/build_school_metrics.py`). The join is real; no number is LLM-produced.

Ops:
  rank_tuition(order: asc|desc, k)    # asc = cheapest first  (official L1 tuition)
  rank_sentiment(order: asc|desc, k)  # desc = most positively reviewed (counted reddit)
combine: intersect | union | null     # intersect for "X that are also Y"
sort_by: tuition | sentiment

Also fixes #20 ("worst reviewed schools") — a single rank_sentiment(order=asc),
rendered deterministically so the order can't be scrambled.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

# ranking/comparison cues that gate the (LLM) planner so single-school questions skip it
_RANK_CUES = re.compile(
    r"\b(cheap(est)?|afford|expensive|price?y|priciest|tuition|best|worst|top|"
    r"most|least|highest|lowest|rank(ed|ing)?|compare|versus|vs\.?|which schools?|"
    r"reviewed|liked|loved|hated|rated|positive|negative)\b", re.I)

_PLAN_PROMPT = (
    "Convert a dental-school question into a typed query PLAN over these ops:\n"
    "- rank_tuition(order: 'asc'|'desc', k)   # asc = cheapest first\n"
    "- rank_sentiment(order: 'asc'|'desc', k) # desc = most positively reviewed first\n"
    "combine: 'intersect' | 'union' | null    # intersect for 'X that are also Y'\n"
    "sort_by: 'tuition' | 'sentiment'\n\n"
    "Return ONLY JSON: "
    '{"ops":[{"op":"...","order":"...","k":0}],"combine":null,"sort_by":"..."}\n'
    "If the question is NOT a ranking/comparison across schools (one named school, or a "
    'topic), return {"ops":[]}.\n\n'
    "Examples:\n"
    'Q: cheapest dental schools -> {"ops":[{"op":"rank_tuition","order":"asc","k":15}],"combine":null,"sort_by":"tuition"}\n'
    'Q: worst reviewed schools -> {"ops":[{"op":"rank_sentiment","order":"asc","k":15}],"combine":null,"sort_by":"sentiment"}\n'
    'Q: cheapest schools that applicants also like -> {"ops":[{"op":"rank_tuition","order":"asc","k":30},{"op":"rank_sentiment","order":"desc","k":50}],"combine":"intersect","sort_by":"tuition"}\n'
    'Q: how do applicants view NYU -> {"ops":[]}\n\n'
    "Q: {q}\nJSON:"
)


def is_ranking_query(question: str) -> bool:
    """Cheap gate: does the question look like a cross-school ranking/comparison?"""
    return bool(_RANK_CUES.search(question or ""))


_LIKED_RE = re.compile(
    r"\b(liked|loved|best[- ]?(reviewed|rated|regarded)|most[- ]?(positive|liked|loved)|"
    r"highly[- ]?(rated|regarded)|well[- ]?regarded|favou?rite)\b|"
    r"(applicants?|students?|people|they)\s+(also\s+)?(like|love|prefer|enjoy)", re.I)
_DISLIKED_RE = re.compile(
    r"\b(worst|least[- ]?liked|most[- ]?negative|hated|lowest[- ]?rated|worst[- ]?reviewed|"
    r"most[- ]?disliked|least[- ]?favou?rite)\b|"
    r"(applicants?|students?|people|they)\s+(also\s+)?(dislike|hate|avoid)", re.I)


def _heuristic_plan(question: str) -> dict:
    """LLM-free fallback plan from keyword cues (also used when no LLM is configured)."""
    q = (question or "").lower()
    cheap = any(w in q for w in ("cheap", "afford", "least expensive", "lowest tuition", "low tuition"))
    pricey = any(w in q for w in ("expensive", "priciest", "highest tuition", "most expensive"))
    liked = bool(_LIKED_RE.search(q))
    disliked = bool(_DISLIKED_RE.search(q))
    paired = (cheap or pricey) and (liked or disliked)
    ops: list[dict] = []
    sort_by = None
    if cheap or pricey:
        ops.append({"op": "rank_tuition", "order": "asc" if cheap else "desc",
                    "k": 30 if paired else 15})
        sort_by = "tuition"
    if liked or disliked:
        ops.append({"op": "rank_sentiment", "order": "desc" if liked else "asc",
                    "k": 50 if paired else 15})
        sort_by = sort_by or "sentiment"
    return {"ops": ops, "combine": "intersect" if len(ops) == 2 else None, "sort_by": sort_by}


def _parse_plan(raw: str) -> dict | None:
    txt = re.sub(r"```(?:json)?", "", raw or "").strip()
    m = re.search(r"\{.*\}", txt, re.DOTALL)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return None
    return d if isinstance(d, dict) and isinstance(d.get("ops"), list) else None


def plan_query(llm, question: str) -> dict:
    """Typed plan for a ranking/comparison question.

    The keyword heuristic is the deterministic FLOOR (it reliably decomposes the common
    cheap/expensive × liked/disliked cases). The LLM only wins when it produces a RICHER
    plan than the heuristic — this stops a small model from under-decomposing
    "cheapest schools applicants also like" down to tuition-only (#35)."""
    heur = _heuristic_plan(question)
    if llm is not None:
        try:
            r = llm.complete(_PLAN_PROMPT.format(q=question), schema=None, temperature=0.0)
            plan = _parse_plan(r.raw_text or "")
            if plan is not None and len(plan.get("ops", [])) > len(heur["ops"]):
                return plan
        except Exception:  # noqa: BLE001 — fall back to heuristic
            pass
    return heur


_COLS = "school_id, name, max_tuition, n_comments, pos_frac"


class SchoolMetrics:
    """Read-only view over the precomputed school_metrics table."""

    def __init__(self, path: str | Path) -> None:
        p = Path(path)
        self.conn = sqlite3.connect(str(p), check_same_thread=False) if p.exists() else None

    def available(self) -> bool:
        return self.conn is not None

    def rank_tuition(self, order: str, k: int) -> list[tuple]:
        if not self.conn:
            return []
        o = "ASC" if order == "asc" else "DESC"
        return self.conn.execute(
            f"SELECT {_COLS} FROM school_metrics WHERE max_tuition IS NOT NULL "  # noqa: S608
            f"ORDER BY max_tuition {o} LIMIT ?", (int(k),)).fetchall()

    def rank_sentiment(self, order: str, k: int, *, min_comments: int = 50) -> list[tuple]:
        if not self.conn:
            return []
        o = "DESC" if order == "desc" else "ASC"
        return self.conn.execute(
            f"SELECT {_COLS} FROM school_metrics WHERE n_comments >= ? "  # noqa: S608
            f"AND pos_frac IS NOT NULL ORDER BY pos_frac {o} LIMIT ?",
            (int(min_comments), int(k))).fetchall()


def execute_plan(plan: dict, metrics: SchoolMetrics, *, display: int = 15) -> dict | None:
    """Run a typed plan deterministically. Returns {plan, ranking:[{school_id, name,
    tuition, n_comments, pos_frac}]} or None if not runnable."""
    ops = plan.get("ops") or []
    if not ops or not metrics.available():
        return None
    lists: list[list[tuple]] = []
    for op in ops:
        order = op.get("order", "asc")
        k = int(op.get("k", 15))
        if op.get("op") == "rank_tuition":
            lists.append(metrics.rank_tuition(order, k))
        elif op.get("op") == "rank_sentiment":
            lists.append(metrics.rank_sentiment(order, k))
    lists = [r for r in lists if r]
    if not lists:
        return None

    rows_by_id = {row[0]: row for r in lists for row in r}
    id_sets = [{row[0] for row in r} for r in lists]
    combine = plan.get("combine")
    if len(id_sets) >= 2 and combine == "intersect":
        keep = set.intersection(*id_sets)
    elif len(id_sets) >= 2 and combine == "union":
        keep = set().union(*id_sets)
    else:
        keep = id_sets[0]

    def _order_for(opname: str, default: str) -> str:
        return next((o.get("order", default) for o in ops if o.get("op") == opname), default)

    merged = [rows_by_id[i] for i in keep]
    sort_by = plan.get("sort_by") or (
        "tuition" if any(o.get("op") == "rank_tuition" for o in ops) else "sentiment")
    if sort_by == "tuition":
        order = _order_for("rank_tuition", "asc")        # asc = cheapest first
        merged = [m for m in merged if m[2] is not None]
        merged.sort(key=lambda m: m[2], reverse=(order == "desc"))
    else:
        order = _order_for("rank_sentiment", "desc")     # asc = worst reviewed first
        merged = [m for m in merged if m[4] is not None]
        merged.sort(key=lambda m: m[4], reverse=(order == "desc"))
    merged = merged[:display]

    return {
        "plan": plan,
        "ranking": [{"school_id": m[0], "name": m[1], "tuition": m[2],
                     "n_comments": m[3], "pos_frac": m[4]} for m in merged],
    }
