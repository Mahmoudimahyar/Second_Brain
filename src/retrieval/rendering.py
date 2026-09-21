"""PV-2: deterministic rendering + entailment guard (anti-fabrication).

Two defenses against the failure where an LLM scrambles a correct list or invents
statistics (#20 "worst reviewed"):

1. **Deterministic rendering** — the grounded answer is assembled by code from the
   counted facts (sentiment %, stance %, L1 facts). The LLM never produces a number or
   an ordering here, so neither can be fabricated or reordered.

2. **Entailment guard** — any LLM free-text we *do* surface (the adjudicator's verdict
   prose) is filtered: a sentence carrying a percentage, or a non-year number that is
   not supported by the counted facts (within a small tolerance), is dropped and
   reported in `filtered_claims`. False-positive drops are preferred to surviving
   fabrications, and every drop is transparent.
"""

from __future__ import annotations

import re

_NUM_RE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")
_SENT_RE = re.compile(r"(?<=[.!?])\s+")


def _parse_num(tok: str) -> tuple[float | None, bool]:
    pct = tok.endswith("%")
    cleaned = tok.replace("$", "").replace(",", "").replace("%", "")
    try:
        return float(cleaned), pct
    except ValueError:
        return None, pct


def numbers_in(text: str) -> list[tuple[float, bool]]:
    """[(value, is_percentage)] for every numeric token in `text`."""
    out: list[tuple[float, bool]] = []
    for m in _NUM_RE.finditer(text or ""):
        v, pct = _parse_num(m.group(0))
        if v is not None:
            out.append((v, pct))
    return out


def best_sentence(query: str, text: str, *, max_len: int = 280) -> str:
    """The single sentence in `text` most relevant to `query` (term overlap), capped.

    Extractive quote selection so a hydrated snippet shows the part that actually
    answers the question, not just the first 280 chars. Falls back to the first
    sentence when there's no term overlap.
    """
    text = (text or "").strip()
    if not text:
        return ""
    sents = [s for s in _SENT_RE.split(text) if s.strip()]
    if not sents:
        return text[:max_len]
    qterms = {w for w in re.findall(r"\w+", query.lower()) if len(w) > 2}
    if not qterms:
        return sents[0][:max_len]
    scored = max(sents, key=lambda s: len(qterms & set(re.findall(r"\w+", s.lower()))))
    overlap = len(qterms & set(re.findall(r"\w+", scored.lower())))
    return (scored if overlap > 0 else sents[0])[:max_len]


def allowed_numbers(facts: dict) -> set[float]:
    """The set of numbers the counted facts actually support (counts, numerators,
    denominators, percentages, and any numbers in L1 fact values)."""
    vals: set[float] = set()

    def add(x: object) -> None:
        try:
            vals.add(round(float(x), 2))
        except (TypeError, ValueError):
            pass

    prov = facts.get("provenance", {}) or {}
    for grp in ("opinion", "sentiment"):
        for s in prov.get(grp, []) or []:
            add(s.get("numerator")); add(s.get("denominator"))
            v = s.get("value")
            if isinstance(v, (int, float)):
                add(round(v * 100)); add(round(v * 100, 1))
    for v in (facts.get("evidence_counts") or {}).values():
        add(v)
    for f in facts.get("l1_facts") or []:
        for val, _pct in numbers_in(str(f.get("value", ""))):
            add(val)
    for k in ("relevant_total", "display_total"):
        if k in facts:
            add(facts[k])
    return vals


def _supported(n: float, allowed: set[float], *, tol_frac: float = 0.02,
               tol_abs: float = 0.5) -> bool:
    return any(abs(a - n) <= max(tol_abs, tol_frac * max(a, n)) for a in allowed)


def _is_year(v: float) -> bool:
    return v == int(v) and 1900 <= v <= 2100


def guard_narration(text: str, allowed: set[float], *, min_flag: float = 10.0
                    ) -> tuple[str, list[str]]:
    """Drop sentences whose statistics aren't supported by `allowed`.

    A number flags its sentence if it is a percentage, or a non-year number >= min_flag,
    that no allowed number matches within tolerance. Returns (clean_text, dropped[]).
    """
    if not text:
        return text, []
    kept: list[str] = []
    dropped: list[str] = []
    for sent in _SENT_RE.split(text.strip()):
        if not sent:
            continue
        bad = [v for v, pct in numbers_in(sent)
               if (pct or (v >= min_flag and not _is_year(v))) and not _supported(v, allowed)]
        (dropped if bad else kept).append(sent)
    return " ".join(kept).strip(), dropped


# -- deterministic rendering -------------------------------------------------

def _fmt_value(predicate: str, value: object) -> str:
    """Human-friendly fact value: currency, percentages, booleans, thousands."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    p = (predicate or "").lower()
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    if n != n:  # NaN
        return str(value)
    if any(w in p for w in ("tuition", "fee", "cost", "salary", "income", "debt")):
        return f"${n:,.0f}"
    if any(w in p for w in ("rate", "pass", "placement", "percent", "pct")):
        return f"{n:g}%"
    if n == int(n):
        return f"{int(n):,}"
    return f"{n:g}"


def render_distribution(stats: list[dict]) -> list[str]:
    """Markdown bullet per bucket — code-built, never LLM-verbalized."""
    out = []
    for s in stats:
        pct = (s.get("value") or 0.0) * 100
        out.append(f"- {pct:.0f}% {s.get('label','')} "
                   f"({s.get('numerator',0):,} of {s.get('denominator',0):,})")
    return out


def render_ranking(result: dict) -> str:
    """Deterministic ranking table (PV-4) — the LLM never produces or reorders it."""
    rows = result.get("ranking", [])
    if not rows:
        return ""
    out = ["**Ranking — computed from official tuition + counted reddit sentiment "
           "(no estimates):**", "",
           "| # | School | Tuition (out-of-state) | Positive sentiment | Comments |",
           "|--:|--------|-----------------------:|-------------------:|---------:|"]
    for i, r in enumerate(rows, 1):
        t = f"${r['tuition']:,.0f}" if r.get("tuition") is not None else "—"
        pf = f"{r['pos_frac'] * 100:.0f}%" if r.get("pos_frac") is not None else "—"
        out.append(f"| {i} | {(r.get('name') or '').title()} | {t} | {pf} "
                   f"| {r.get('n_comments', 0):,} |")
    out += ["", "_Tuition from official L1 data; positive sentiment is a real count over "
            "each school's reddit comments. Use each row's drill-down to inspect the exact "
            "comments behind its percentage._"]
    return "\n".join(out)


def render_facets(question: str, facets: dict) -> str:
    """Deterministic sub-topic breakdown (PV-5) — counted over query-scoped docs."""
    rows = facets.get("subtopics", [])
    if not rows:
        return ""
    total = facets.get("classified", facets.get("n_total", 0))
    out = [f"**Sub-topics — clustered from {total:,} query-relevant forum docs (counted):**", ""]
    for r in rows:
        out.append(f"- **{r['label']}** — {r['fraction'] * 100:.0f}% ({r['n']:,} docs): "
                   f"{r.get('description', '')}")
    out += ["", "_Each sub-topic is a real count over the docs retrieved for this query "
            "(not global clusters); drill down to inspect the exact posts/comments._"]
    return "\n".join(out)


def render_grounded_answer(dossier: dict) -> str:
    """A faithful answer assembled purely from the counted facts (no LLM in the number
    or ordering path). Shown alongside the verdict as the trustworthy surface."""
    out: list[str] = []
    if not dossier.get("answered", True) and dossier.get("abstain_reason"):
        out.append(f"_Not enough official/consensus evidence to adjudicate: "
                   f"{dossier['abstain_reason']}. The counted breakdown below still holds._\n")

    l1 = dossier.get("l1_facts") or []
    if l1:
        out.append("**Official facts (L1):**")
        for f in l1[:8]:
            src = f.get("source") or f.get("url") or "official source"
            name = str(f.get("predicate", "")).replace("_", " ")
            out.append(f"- {name}: {_fmt_value(f.get('predicate', ''), f.get('value', ''))}"
                       f"  _(source: {src})_")
        out.append("")

    prov = dossier.get("provenance", {}) or {}
    sent = prov.get("sentiment") or []
    if sent:
        out.append(f"**Sentiment over {sent[0]['denominator']:,} reddit comments (counted, not estimated):**")
        out += render_distribution(sent)
        out.append("")
    op = prov.get("opinion") or []
    if op:
        out.append(f"**Main positions (counted over {op[0]['denominator']:,} relevant docs):**")
        out += render_distribution(op)
        out.append("")

    v = dossier.get("verdict") or {}
    if dossier.get("answered", True) and v.get("authoritative_answer"):
        out.append(f"**Verdict:** {v['authoritative_answer']}")
        out.append("")

    out.append("_Every percentage is a real count; use each statistic's drill-down link "
               "to inspect the exact posts/comments behind it._")
    return "\n".join(out).strip()
