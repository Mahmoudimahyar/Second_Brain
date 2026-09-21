"""ED-5: counted stance clustering — the real 80/15/5.

Decision #2 (`project_evidence_dossier`: always counted, never estimated). The LLM
only NAMES 2-4 distinct positions from a sample of the relevant forum text. The
**fractions are a real tally**: every doc in the full relevant forum set is classified
to its nearest position by embedding cosine, then counted. No LLM-guessed percentages.

This is the difference between "the model thinks ~80% agree" and "of 3,224 relevant
comments, 2,322 (72%) align with position A" — the latter is reproducible from vectors.
"""

from __future__ import annotations

import json
import re

import numpy as np

_POS_PROMPT = (
    "You are analyzing dental-school applicant forum opinions on this question:\n"
    '"{q}"\n\nRepresentative forum excerpts:\n{snips}\n\n'
    "Identify the 2-4 DISTINCT positions people take — actual viewpoints/stances, not "
    "sentiment polarity. Make them mutually distinct and collectively cover the excerpts.\n"
    'Return ONLY a JSON array: [{{"label": "<short stance>", "description": "<one sentence>"}}].'
)


def _parse_positions(raw: str, max_positions: int) -> list[dict]:
    """Tolerant parse of a JSON position array (handles markdown fences / trailing prose)."""
    txt = re.sub(r"```(?:json)?", "", raw or "").strip()
    m = re.search(r"\[.*\]", txt, re.DOTALL)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(arr, list):
        return []
    out = [{"label": str(p.get("label", "")).strip(),
            "description": str(p.get("description", "")).strip()}
           for p in arr if isinstance(p, dict) and p.get("label")]
    return out[:max_positions]


def derive_positions(
    llm, question: str, snippets: list[str], *, max_positions: int = 4, attempts: int = 2,
) -> list[dict]:
    """Ask the LLM to name 2-4 stance positions from sample excerpts (no percentages).

    Robust to the flakiness that previously dropped the opinion distribution: attempt 1
    runs at temperature 0 (reproducible); on an empty/unparseable result or a transient
    error it retries once at 0.3 (breaks a deterministic bad-format loop). Parsing
    tolerates markdown fences and trailing prose.
    """
    snips = "\n".join(f"- {s[:200]}" for s in snippets[:40])
    prompt = _POS_PROMPT.format(q=question, snips=snips)
    for i in range(max(1, attempts)):
        try:
            r = llm.complete(prompt, schema=None, temperature=0.0 if i == 0 else 0.3)
            pos = _parse_positions(r.raw_text or "", max_positions)
            if pos:
                return pos
        except Exception:  # noqa: BLE001
            continue
    return []


def classify_counted(
    store, items: list[dict], doc_ids: list[str], *, min_sim: float = 0.15,
) -> tuple[list[dict], int, int, int]:
    """Classify every doc to its nearest item (label+description prototype) by embedding
    cosine and COUNT — the shared counted-distribution kernel for stance positions and
    facet sub-topics (PV-5). Returns (dist, classified, unclear, n_total) where each dist
    row carries the FULL doc_id set (PV-1) sorted by size.
    """
    proto = np.array(
        [store.embed_query(f"{p['label']}. {p['description']}") for p in items],
        dtype=np.float32,
    )
    ids, mat = store.vectors_for(doc_ids)
    if mat.shape[0] == 0:
        zero = [{"label": p["label"], "description": p["description"], "n": 0,
                 "fraction": 0.0, "example_ids": [], "doc_ids": []} for p in items]
        return zero, 0, 0, 0

    sims = mat @ proto.T                 # (N, K)
    best = sims.argmax(axis=1)
    best_sim = sims.max(axis=1)
    bucket_ids: list[list[str]] = [[] for _ in items]   # FULL id set per item (PV-1)
    unclear = 0
    for i in range(len(ids)):
        if best_sim[i] < min_sim:
            unclear += 1
            continue
        bucket_ids[int(best[i])].append(ids[i])

    classified = sum(len(b) for b in bucket_ids)
    denom = classified or 1
    dist = [{"label": items[k]["label"], "description": items[k]["description"],
             "n": len(bucket_ids[k]), "fraction": round(len(bucket_ids[k]) / denom, 3),
             "example_ids": bucket_ids[k][:3], "doc_ids": bucket_ids[k]}
            for k in range(len(items))]
    dist.sort(key=lambda x: -x["n"])
    return dist, classified, unclear, len(ids)


def stance_distribution(
    store, llm, question: str, forum_doc_ids: list[str], snippet_fn,
    *, sample: int = 40, min_sim: float = 0.15,
) -> dict:
    """Counted stance distribution over the full relevant forum set.

    `snippet_fn(ids) -> {id: text}` supplies sample text for position derivation.
    Returns {positions: [{label, description, n, fraction, example_ids, doc_ids}],
    classified, unclear, n_total} — fractions are over the classified (non-unclear) docs.
    """
    if not forum_doc_ids:
        return {"positions": [], "classified": 0, "n_total": 0, "note": "no evidence"}

    snip_map = snippet_fn(forum_doc_ids[:sample])
    snippets = [t for t in (snip_map.get(d, "") for d in forum_doc_ids[:sample]) if t]
    if not snippets:
        return {"positions": [], "classified": 0, "n_total": 0, "note": "no sample text"}

    positions = derive_positions(llm, question, snippets)
    if not positions:
        return {"positions": [], "classified": 0, "n_total": 0, "note": "no positions derived"}

    dist, classified, unclear, n_total = classify_counted(
        store, positions, forum_doc_ids, min_sim=min_sim)
    return {"positions": dist, "classified": classified, "unclear": unclear,
            "n_total": n_total}
