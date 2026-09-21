"""Finer topic granularity — data-driven clustering (BERTopic-style).

The old path asked the LLM to name 3-6 topics, then assigned every doc to its nearest
label by cosine — so a vague, central label absorbed the majority (the 75% catch-all).
Here we cluster the document EMBEDDINGS into K balanced clusters first (spherical k-means,
the right metric for normalized vectors), then label each cluster from its centroid
members. No single vague prototype can dominate, and K is tunable for granularity.

numpy-only + seeded -> deterministic and portable. Labels are batch-LLM'd (one call) and
cached for reproducibility.
"""

from __future__ import annotations

import numpy as np

from src.retrieval.stance import _parse_positions


def _kmeans_spherical(mat: np.ndarray, k: int, *, seed: int = 0, iters: int = 50):
    """Spherical k-means on L2-normalized rows (assignment = max dot product). k-means++
    seeding for stable, balanced clusters."""
    n = mat.shape[0]
    k = max(2, min(k, n))
    rng = np.random.default_rng(seed)
    centers = [mat[int(rng.integers(n))]]
    for _ in range(1, k):
        d = np.min(np.stack([1.0 - mat @ c for c in centers]), axis=0)
        d = np.clip(d, 0, None)
        probs = d / d.sum() if d.sum() > 1e-9 else None
        centers.append(mat[int(rng.choice(n, p=probs))])
    c_mat = np.array(centers, dtype=np.float32)
    labels = np.zeros(n, dtype=int)
    for _ in range(iters):
        new_labels = np.argmax(mat @ c_mat.T, axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for j in range(k):
            sel = mat[labels == j]
            if sel.shape[0]:
                v = sel.mean(axis=0)
                c_mat[j] = v / max(float(np.linalg.norm(v)), 1e-9)
    return labels, c_mat


def _label_clusters(llm, cluster_snippets: list[list[str]], *, cache=None, cache_key=None):
    """One LLM call labels all clusters (distinct labels, sees them together). Cached."""
    if cache is not None and cache_key:
        cached = cache.get(cache_key)
        if cached:
            return cached
    blocks = []
    for i, snips in enumerate(cluster_snippets):
        sample = " || ".join(s[:120].replace("\n", " ") for s in snips[:5] if s)
        blocks.append(f"[{i}] {sample}")
    prompt = (f"Below are {len(blocks)} clusters of dental-applicant forum excerpts. For EACH "
              f"cluster give a SHORT distinct topic label (2-4 words) + a one-sentence "
              f"description.\n\n" + "\n".join(blocks) +
              f"\n\nReturn ONLY a JSON array of exactly {len(blocks)} objects "
              f'[{{"label":"..","description":".."}}] in the SAME order as the clusters.')
    labs: list[dict] = []
    try:
        r = llm.complete(prompt, schema=None, temperature=0.0)
        labs = _parse_positions(r.raw_text or "", len(blocks) + 10)
    except Exception:  # noqa: BLE001
        labs = []
    while len(labs) < len(cluster_snippets):
        labs.append({"label": f"Topic {len(labs) + 1}", "description": ""})
    labs = labs[:len(cluster_snippets)]
    if cache is not None and cache_key:
        cache.set(cache_key, labs)
    return labs


def top_cluster_fraction(store, doc_ids: list[str], *, k: int = 10, seed: int = 1,
                         min_cluster: int = 5) -> float | None:
    """Largest-cluster share under a (different) seed — a label-free cluster-stability
    check for robustness (no LLM call)."""
    ids, mat = store.vectors_for(doc_ids)
    if mat.shape[0] < 4:
        return None
    k = max(2, min(k, mat.shape[0] // min_cluster or 2))
    labels, _ = _kmeans_spherical(mat, k, seed=seed)
    counts = np.bincount(labels, minlength=k)
    return round(float(counts.max()) / float(counts.sum()), 4)


def kmeans_topics(store, llm, doc_ids: list[str], *, k: int = 12, cache=None,
                  cache_key=None, snippet_fn=None, min_cluster: int = 5, seed: int = 0
                  ) -> list[dict]:
    """K balanced, labeled topic clusters over the docs' embeddings. Returns rows shaped
    like classify_counted: [{label, description, n, fraction, doc_ids, example_ids}]."""
    ids, mat = store.vectors_for(doc_ids)
    if mat.shape[0] < 4:
        return []
    k = max(2, min(k, mat.shape[0] // min_cluster or 2))
    labels, c_mat = _kmeans_spherical(mat, k, seed=seed)
    members: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        members.setdefault(int(lab), []).append(i)
    keep = [(c, idxs) for c, idxs in members.items() if len(idxs) >= min_cluster]

    cluster_snippets = []
    for c, idxs in keep:
        sims = mat[idxs] @ c_mat[c]
        top = [ids[idxs[j]] for j in np.argsort(-sims)[:6]]
        sm = snippet_fn(top) if snippet_fn else {}
        cluster_snippets.append([sm.get(t, "") for t in top])
    labs = _label_clusters(llm, cluster_snippets, cache=cache, cache_key=cache_key)

    out = []
    for (_c, idxs), lab in zip(keep, labs):
        mids = [ids[i] for i in idxs]
        out.append({"label": lab["label"], "description": lab.get("description", ""),
                    "doc_ids": mids, "n": len(mids), "example_ids": mids[:3]})
    total = sum(o["n"] for o in out) or 1
    for o in out:
        o["fraction"] = round(o["n"] / total, 3)
    out.sort(key=lambda x: -x["n"])
    return out
