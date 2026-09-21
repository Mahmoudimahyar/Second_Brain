"""M3 signals — operationalize abstract criteria (e.g. virality) as measurable corpus
signals over a topic's documents.

These are honest PROXIES, not platform metrics: forum sentiment/score/text, not
Instagram/TikTok reach. The concept path (protocol._concept) min-max normalizes them
across the candidate topics, so each signal is a *relative* ranking within one query.

  emotion_intensity  -> high-arousal emotion (Berger & Milkman): non-neutral sentiment rate
  engagement_score   -> shares/saves proxy: p90 comment score
  advice_density     -> practical value: how-to / advice language
  narrative_density  -> stories: first-person / experience language
  social_currency    -> status signalling: acceptance / stats / achievement language
"""

from __future__ import annotations

import statistics

from src.research.enrich import year_of

_ADVICE = ("how to", "how do", "how did", "should i", "recommend", "tip", "advice",
           "make sure", "you need", "best way", "guide", "step", "study for", "prepare")
_STORY = ("i ", "my ", "me ", "i was", "i got", "i had", "i felt", "when i", "experience",
          "i remember", "i ended up", "for me")
_STATUS = ("got in", "got into", "accepted", "acceptance", "admitted", "gpa", "dat",
           "scored", "stats", "waitlist", "interview invite", "ii ", "matriculat")


def _density(texts: list[str], lex: tuple[str, ...]) -> float:
    if not texts:
        return 0.0
    return sum(1 for t in texts if any(w in t for w in lex)) / len(texts)


def compute_signals(engine, doc_ids: list[str], *, sample: int = 1500) -> dict:
    """Raw viral-fit signals for one topic's document set (capped for speed)."""
    ids = doc_ids[:sample]
    if not ids:
        return {"emotion_intensity": 0.0, "engagement_score": 0.0, "advice_density": 0.0,
                "narrative_density": 0.0, "social_currency": 0.0, "n_signal": 0}
    sent = engine.reader.sentiment_for(ids)
    tot = sum(len(v) for v in sent.values())
    emotion = (1 - len(sent.get("neutral", [])) / tot) if tot else 0.0

    texts: list[str] = []
    scores: list[float] = []
    years: list[int] = []
    for i in range(0, len(ids), 400):
        batch = ids[i:i + 400]
        marks = ",".join("?" * len(batch))
        for _d, t, s, ci in engine.docs.execute(
            f"SELECT doc_id, lower(substr(text,1,400)), score, created_iso "  # noqa: S608
            f"FROM documents WHERE doc_id IN ({marks})", batch):
            texts.append(t or "")
            if s is not None:
                scores.append(float(s))
            y = year_of(ci)
            if y:
                years.append(y)
    p90 = (statistics.quantiles(scores, n=10)[-1] if len(scores) > 10
           else (max(scores) if scores else 0.0))
    recency = (sum(1 for y in years if y >= 2020) / len(years)) if years else 0.0
    return {
        "emotion_intensity": round(emotion, 4),
        "engagement_score": round(float(p90), 2),
        "advice_density": round(_density(texts, _ADVICE), 4),
        "narrative_density": round(_density(texts, _STORY), 4),
        "social_currency": round(_density(texts, _STATUS), 4),
        "recency": round(recency, 4),
        "n_signal": len(texts),
    }


def minmax_normalize(rows: list[dict], keys: list[str]) -> list[dict]:
    """Min-max normalize each signal across the candidate topics -> comparable [0,1]."""
    out = [dict(r) for r in rows]
    for k in keys:
        vals = [r.get(k, 0.0) or 0.0 for r in rows]
        lo, hi = min(vals), max(vals)
        rng = hi - lo
        for r in out:
            r[f"{k}_norm"] = round(((r.get(k, 0.0) or 0.0) - lo) / rng, 4) if rng > 1e-9 else 0.0
    return out
