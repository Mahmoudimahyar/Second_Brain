"""Build the ~10K-node bake-off sample subgraph.

Reads:
  - 5 most-recent ADEA Excel files under `External Data\\Official Dental School Data\\Report 2_*\\`
  - r/DentalSchool JSONL files under `External Data\\Forum\\Reddit\\`

Produces:
  - ~500 L1 nodes (Schools + School-year-metrics + CycleYears)
  - ~5,000 L5 Posts (subsampled deterministically by upvote-quartile)
  - ~3,500 L5 Users (derived from post authors)
  - ~1,000 derived Topic / Claim nodes
  - all V1 property-convention fields on every edge

Also generates synthetic 384-d vectors for HNSW recall testing (per `tools/bake_off/schema.py`).

Output is pickled to `data/bake_off/sample.pkl` for reuse across candidate drivers.
"""

from __future__ import annotations

import hashlib
import json
import pickle
import random
import re
from datetime import UTC, datetime
from pathlib import Path

import openpyxl
import orjson

from tools.bake_off.schema import (
    Sample,
    SampleEdge,
    SampleEmbedding,
    SampleNode,
)

_RNG = random.Random(42)


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s or "unknown"


def _now() -> datetime:
    return datetime.now(UTC)


def _hash_id(prefix: str, *parts: str) -> str:
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{h}"


def build_l1_from_adea(adea_dir: Path, max_files: int = 5) -> tuple[list[SampleNode], list[SampleEdge]]:
    """Walk ADEA Report 2 Excel files. Build School + Metric nodes + SCHOOL_HAS_METRIC edges."""

    nodes: list[SampleNode] = []
    edges: list[SampleEdge] = []
    seen_schools: dict[str, str] = {}  # canonical_name → school_id
    now = _now()

    files = sorted(adea_dir.glob("*.xlsx"))[-max_files:]
    for xlsx in files:
        cycle = _extract_cycle_from_filename(xlsx.name)
        if cycle is None:
            continue
        cycle_id = f"cycle:{cycle}"
        nodes.append(
            SampleNode(
                id=cycle_id,
                label="CycleYear",
                source_tier="L1",
                properties={"cycle": cycle},
            )
        )
        wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
        # Walk each sheet; collect rows where a "School" or "Institution" column exists.
        for ws in wb.worksheets:
            header_row = _find_header_row(ws)
            if header_row is None:
                continue
            headers = [str(c.value).strip() if c.value else "" for c in header_row]
            school_col = _find_col(headers, ("School", "Institution", "Dental School"))
            if school_col is None:
                continue
            metric_cols = _find_metric_cols(headers)
            for row_cells in ws.iter_rows(min_row=header_row[0].row + 1, values_only=True):
                if school_col >= len(row_cells):
                    continue
                school_name = row_cells[school_col]
                if not isinstance(school_name, str) or not school_name.strip():
                    continue
                slug = _slugify(school_name)
                school_id = seen_schools.get(slug)
                if school_id is None:
                    school_id = f"school:{slug}"
                    seen_schools[slug] = school_id
                    nodes.append(
                        SampleNode(
                            id=school_id,
                            label="School",
                            source_tier="L1",
                            properties={"canonical_name": school_name.strip(), "slug": slug},
                        )
                    )
                # Emit one Metric node per (school, cycle, metric).
                for col_idx, metric_name in metric_cols:
                    if col_idx >= len(row_cells):
                        continue
                    value = row_cells[col_idx]
                    if value is None or value == "":
                        continue
                    metric_id = _hash_id("metric", school_id, cycle, metric_name)
                    nodes.append(
                        SampleNode(
                            id=metric_id,
                            label="Metric",
                            source_tier="L1",
                            properties={
                                "school_id": school_id,
                                "cycle": cycle,
                                "metric_name": metric_name,
                                "value": str(value),
                            },
                        )
                    )
                    edges.append(
                        SampleEdge(
                            id=f"e:scm:{school_id}:{metric_id}",
                            relation="SCHOOL_HAS_METRIC",
                            from_id=school_id,
                            to_id=metric_id,
                            source_tier="L1",
                            rank="preferred",
                            references=[xlsx.name],
                            qualifiers={"cycle": cycle},
                            t_valid_from=_cycle_to_date(cycle, start=True),
                            t_valid_to=_cycle_to_date(cycle, start=False),
                            t_ingest_from=now,
                            created_utc=now,
                        )
                    )
        wb.close()
    return nodes, edges


def _extract_cycle_from_filename(name: str) -> str | None:
    m = re.search(r"(20\d{2})[\-_](\d{2})", name)
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}"


def _cycle_to_date(cycle: str, start: bool) -> datetime:
    year_part = cycle.split("-", maxsplit=1)[0]
    year = int(year_part)
    if start:
        return datetime(year, 9, 1, tzinfo=UTC)
    return datetime(year + 1, 8, 31, tzinfo=UTC)


def _find_header_row(ws) -> tuple | None:  # type: ignore[no-untyped-def]
    """Scan the first ~15 rows for one that looks like headers (≥3 non-empty string cells)."""

    for _i, row in enumerate(ws.iter_rows(max_row=15), start=1):
        non_empty_strings = sum(
            1 for c in row if isinstance(c.value, str) and c.value.strip()
        )
        if non_empty_strings >= 3:
            return row
    return None


def _find_col(headers: list[str], aliases: tuple[str, ...]) -> int | None:
    norm = [h.strip().lower() for h in headers]
    for alias in aliases:
        if alias.lower() in norm:
            return norm.index(alias.lower())
    return None


def _find_metric_cols(headers: list[str]) -> list[tuple[int, str]]:
    """Identify columns whose headers look like metric names (tuition/DAT/GPA/etc.)."""

    keywords = ("tuition", "dat", "gpa", "applicant", "enrolled", "interview", "acceptance", "cost")
    out: list[tuple[int, str]] = []
    for i, h in enumerate(headers):
        if not h or not isinstance(h, str):
            continue
        hl = h.lower()
        if any(k in hl for k in keywords):
            out.append((i, h.strip()))
    return out


def build_l5_from_reddit(
    reddit_dir: Path,
    *,
    max_posts: int = 5000,
    max_comments_per_post: int = 5,
) -> tuple[list[SampleNode], list[SampleEdge]]:
    """Subsample r/DentalSchool posts (stratified by upvote quartile) + a handful of comments each."""

    posts_path = reddit_dir / "r_DentalSchool_posts.jsonl"
    comments_path = reddit_dir / "r_DentalSchool_comments.jsonl"
    nodes: list[SampleNode] = []
    edges: list[SampleEdge] = []
    if not posts_path.exists():
        return nodes, edges

    # Pass 1: load posts, keep ids + score for stratified sampling.
    posts_pool: list[dict] = []
    with posts_path.open("rb") as f:
        for line in f:
            try:
                obj = orjson.loads(line)
            except orjson.JSONDecodeError:
                continue
            if not isinstance(obj, dict) or "id" not in obj:
                continue
            posts_pool.append(obj)

    sampled = _stratified_sample(posts_pool, max_posts)
    post_ids: set[str] = set()
    seen_users: set[str] = set()
    now = _now()
    sub_id = "subreddit:DentalSchool"
    nodes.append(
        SampleNode(id=sub_id, label="Subreddit", source_tier="L5", properties={"name": "DentalSchool"})
    )

    for p in sampled:
        post_id = f"reddit_post:{p['id']}"
        author = p.get("author") or "[deleted]"
        user_id = f"reddit:DentalSchool:{author}"
        if user_id not in seen_users:
            seen_users.add(user_id)
            nodes.append(SampleNode(id=user_id, label="User", source_tier="L5", properties={"author": author}))
        post_ids.add(p["id"])
        created_utc = datetime.fromtimestamp(int(p.get("created_utc", 0) or 0), tz=UTC)
        nodes.append(
            SampleNode(
                id=post_id,
                label="Post",
                source_tier="L5",
                properties={
                    "title": p.get("title", "")[:300],
                    "selftext": (p.get("selftext") or "")[:1000],
                    "score": int(p.get("score", 0) or 0),
                    "ups": int(p.get("ups", 0) or 0),
                    "downs": int(p.get("downs", 0) or 0),
                    "num_comments": int(p.get("num_comments", 0) or 0),
                    "created_utc": created_utc.isoformat(),
                    "flair": p.get("link_flair_text") or "",
                },
            )
        )
        edges.append(
            SampleEdge(
                id=f"e:auth:{user_id}:{post_id}",
                relation="AUTHORED",
                from_id=user_id,
                to_id=post_id,
                source_tier="L5",
                rank="normal",
                references=[p["id"]],
                t_valid_from=created_utc,
                t_ingest_from=now,
                created_utc=created_utc,
            )
        )
        edges.append(
            SampleEdge(
                id=f"e:in:{post_id}:{sub_id}",
                relation="POSTED_IN_FORUM",
                from_id=post_id,
                to_id=sub_id,
                source_tier="L5",
                rank="normal",
                references=[p["id"]],
                t_valid_from=created_utc,
                t_ingest_from=now,
                created_utc=created_utc,
            )
        )

    # Pass 2: stream comments, keep only those whose link_id matches a sampled post.
    if comments_path.exists():
        kept_per_post: dict[str, int] = {}
        with comments_path.open("rb") as f:
            for line in f:
                try:
                    obj = orjson.loads(line)
                except orjson.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                link_id = obj.get("link_id", "") or ""
                if not link_id.startswith("t3_"):
                    continue
                root_id = link_id[3:]
                if root_id not in post_ids:
                    continue
                if kept_per_post.get(root_id, 0) >= max_comments_per_post:
                    continue
                kept_per_post[root_id] = kept_per_post.get(root_id, 0) + 1
                comment_id = f"reddit_comment:{obj['id']}"
                author = obj.get("author") or "[deleted]"
                user_id = f"reddit:DentalSchool:{author}"
                if user_id not in seen_users:
                    seen_users.add(user_id)
                    nodes.append(SampleNode(id=user_id, label="User", source_tier="L5", properties={"author": author}))
                created_utc = datetime.fromtimestamp(int(obj.get("created_utc", 0) or 0), tz=UTC)
                nodes.append(
                    SampleNode(
                        id=comment_id,
                        label="Comment",
                        source_tier="L5",
                        properties={
                            "body": (obj.get("body") or "")[:1000],
                            "score": int(obj.get("score", 0) or 0),
                            "ups": int(obj.get("ups", 0) or 0),
                            "created_utc": created_utc.isoformat(),
                        },
                    )
                )
                edges.append(
                    SampleEdge(
                        id=f"e:auth:{user_id}:{comment_id}",
                        relation="AUTHORED",
                        from_id=user_id,
                        to_id=comment_id,
                        source_tier="L5",
                        rank="normal",
                        references=[obj["id"]],
                        t_valid_from=created_utc,
                        t_ingest_from=now,
                        created_utc=created_utc,
                    )
                )
                edges.append(
                    SampleEdge(
                        id=f"e:rep:{comment_id}:reddit_post:{root_id}",
                        relation="REPLIED_TO",
                        from_id=comment_id,
                        to_id=f"reddit_post:{root_id}",
                        source_tier="L5",
                        rank="normal",
                        references=[obj["id"]],
                        t_valid_from=created_utc,
                        t_ingest_from=now,
                        created_utc=created_utc,
                    )
                )

    return nodes, edges


def _stratified_sample(items: list[dict], total: int) -> list[dict]:
    if len(items) <= total:
        return list(items)
    items_sorted = sorted(items, key=lambda x: int(x.get("score", 0) or 0))
    n = len(items_sorted)
    quartiles = [
        items_sorted[0 : n // 4],
        items_sorted[n // 4 : n // 2],
        items_sorted[n // 2 : (3 * n) // 4],
        items_sorted[(3 * n) // 4 :],
    ]
    per_quartile = total // 4
    out: list[dict] = []
    for q in quartiles:
        out.extend(_RNG.sample(q, k=min(per_quartile, len(q))))
    return out[:total]


def build_topic_edges(
    school_nodes: list[SampleNode],
    post_nodes: list[SampleNode],
    *,
    max_mentions: int = 1000,
) -> tuple[list[SampleNode], list[SampleEdge]]:
    """Generate `MENTIONS_SCHOOL` edges by simple title/body keyword match.

    Cheap signal for the bake-off — not the real entity-resolution pipeline.
    """

    nodes: list[SampleNode] = []
    edges: list[SampleEdge] = []
    now = _now()
    school_keywords: list[tuple[str, str]] = []
    for s in school_nodes:
        name = str(s.properties.get("canonical_name", ""))
        head = name.split(" ", 1)[0].lower()
        if len(head) >= 4:
            school_keywords.append((s.id, head))

    count = 0
    for p in post_nodes:
        if count >= max_mentions:
            break
        text = ((p.properties.get("title", "") or "") + " " + (p.properties.get("selftext", "") or "")).lower()
        for school_id, head in school_keywords:
            if head in text:
                edges.append(
                    SampleEdge(
                        id=f"e:ms:{p.id}:{school_id}",
                        relation="MENTIONS_SCHOOL",
                        from_id=p.id,
                        to_id=school_id,
                        source_tier="L5",
                        rank="normal",
                        references=[p.id],
                        qualifiers={"confidence": 0.85},
                        t_ingest_from=now,
                        created_utc=now,
                        confidence=0.85,
                    )
                )
                count += 1
                if count >= max_mentions:
                    break
    return nodes, edges


def build_embeddings(
    chunk_ids: list[str],
    *,
    dim: int = 384,
    query_count: int = 500,
    rng_seed: int = 42,
) -> tuple[list[SampleEmbedding], list[SampleEmbedding], dict[str, list[str]]]:
    """Generate synthetic 384-d vectors + brute-force top-10 ground truth.

    Vectors are normalized; recall@10 is computed against cosine similarity.
    """

    rng = random.Random(rng_seed)
    embeddings = [_random_unit_vector(cid, dim, rng) for cid in chunk_ids]
    query_chunks = rng.sample(chunk_ids, k=min(query_count, len(chunk_ids)))
    queries = [SampleEmbedding(chunk_id=f"q:{cid}", vector=_random_unit_vector(cid, dim, rng).vector) for cid in query_chunks]
    # Brute-force top-10 by cosine similarity.
    truth: dict[str, list[str]] = {}
    emb_by_id = {e.chunk_id: e.vector for e in embeddings}
    for q in queries:
        scored = sorted(
            ((cid, _cosine(q.vector, vec)) for cid, vec in emb_by_id.items()),
            key=lambda kv: kv[1],
            reverse=True,
        )
        truth[q.chunk_id] = [cid for cid, _ in scored[:10]]
    return embeddings, queries, truth


def _random_unit_vector(seed_str: str, dim: int, rng: random.Random) -> SampleEmbedding:
    # Deterministic per chunk_id-prefix so chunks with shared prefix cluster naturally.
    local_rng = random.Random(seed_str)
    raw = [local_rng.gauss(0.0, 1.0) for _ in range(dim)]
    norm = sum(x * x for x in raw) ** 0.5 or 1.0
    return SampleEmbedding(chunk_id=seed_str, vector=[x / norm for x in raw])


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def build_sample(
    *,
    repo_root: Path,
    out_path: Path,
    max_posts: int = 5000,
    embedding_count: int = 5000,
    query_count: int = 200,
) -> Sample:
    adea_dir = repo_root / "External Data" / "Official Dental School Data" / "Report 2_ Tuition, Admission, and Attrition"
    reddit_dir = repo_root / "External Data" / "Forum" / "Reddit"

    l1_nodes, l1_edges = build_l1_from_adea(adea_dir)
    l5_nodes, l5_edges = build_l5_from_reddit(reddit_dir, max_posts=max_posts)
    school_nodes = [n for n in l1_nodes if n.label == "School"]
    post_nodes = [n for n in l5_nodes if n.label == "Post"]
    topic_nodes, topic_edges = build_topic_edges(school_nodes, post_nodes)

    all_nodes = l1_nodes + l5_nodes + topic_nodes
    all_edges = l1_edges + l5_edges + topic_edges

    # Embedding chunks: every Post + Comment body.
    chunk_ids = [n.id for n in all_nodes if n.label in {"Post", "Comment"}][:embedding_count]
    embeddings, query_vectors, ground_truth = build_embeddings(chunk_ids, query_count=query_count)

    sample = Sample(
        nodes=all_nodes,
        edges=all_edges,
        embeddings=embeddings,
        query_vectors=query_vectors,
        ground_truth_top10=ground_truth,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as f:
        pickle.dump(sample, f)

    # Also save a small summary JSON for quick inspection.
    summary = {
        "nodes_total": len(all_nodes),
        "edges_total": len(all_edges),
        "embeddings_total": len(embeddings),
        "queries": len(query_vectors),
        "node_label_counts": _label_counts(all_nodes),
        "edge_relation_counts": _relation_counts(all_edges),
    }
    out_path.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2))
    return sample


def _label_counts(nodes: list[SampleNode]) -> dict[str, int]:
    out: dict[str, int] = {}
    for n in nodes:
        out[n.label] = out.get(n.label, 0) + 1
    return out


def _relation_counts(edges: list[SampleEdge]) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in edges:
        out[e.relation] = out.get(e.relation, 0) + 1
    return out


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--out", default="data/bake_off/sample.pkl")
    parser.add_argument("--max-posts", type=int, default=5000)
    parser.add_argument("--embedding-count", type=int, default=5000)
    parser.add_argument("--query-count", type=int, default=200)
    args = parser.parse_args()
    sample = build_sample(
        repo_root=Path(args.repo).resolve(),
        out_path=Path(args.out),
        max_posts=args.max_posts,
        embedding_count=args.embedding_count,
        query_count=args.query_count,
    )
    print(
        f"sample built: nodes={len(sample.nodes)} edges={len(sample.edges)} "
        f"embeddings={len(sample.embeddings)} queries={len(sample.query_vectors)}"
    )
