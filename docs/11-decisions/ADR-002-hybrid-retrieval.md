# ADR-002: Hybrid Retrieval (HNSW + BM25 + RRF)

Status: **accepted** — architecture-shape locked; concrete BM25 engine tied to ADR-001 winner
Date: 2026-05-20

## Context

Retrieval over the trust-tier-aware multi-layer graph requires three signal sources fused together: graph traversal (structural), dense vector ANN (semantic), and BM25 (lexical). R-002 (R-006 verified) compared pgvector / Qdrant / Weaviate / LanceDB / sqlite-vec / Kùzu-native / Neo4j-native vector indexes.

Verdict: **at V1 scale (<5M chunks, internal use, single-node)**, the graph DB's native HNSW is sufficient. Sidecar systems (Qdrant) add ops cost without clear benefit until recall fails or filtered-ANN throughput becomes a bottleneck.

## Decision

**HNSW + BM25 + Reciprocal Rank Fusion in Python.** Specifically:

- **Dense vector**: HNSW native to the graph DB chosen in ADR-001. `M=16`, `ef_construction=200`, `ef_search=64` as round-1 defaults (tuned later).
- **BM25**: Tantivy (if LadybugDB / Graphiti+Neo4j wins) OR Postgres FTS via `tsvector` + `pg_trgm` (if Postgres+AGE wins). Decision tied to ADR-001.
- **Fusion**: Reciprocal Rank Fusion (~30 lines of Python in `src/retrieval/rrf.py`) merges the two ranked lists. Standard RRF formula: `score(d) = Σ_q 1 / (k + rank_q(d))` with k=60 default.
- **Embedding model**: `BAAI/bge-small-en-v1.5` (384-d). ONNX runtime for CPU; CUDA for GPU when available.
- **Filter pre-pass**: graph traversal filters by `source_tier`, time range, `as_of`, then ANN runs over the filtered candidate set.

## Escalation rule

Switch to a sidecar **Qdrant** only if:
- HNSW recall@10 < 0.85 on the V1 eval set after one round of tuning, OR
- Filtered-ANN throughput becomes a bottleneck (QPS > 50 at V1 scale, which is unlikely; reassess at corpus > 5M chunks).

Switching cost: ~1 week of work — `src/retrieval/` interface stays stable, only the vector backend changes.

## Consequences

- One fewer service to operate in V1 (native HNSW lives inside the graph DB).
- Re-build vector index nightly from canonical embeddings stored as Parquet (`embedding_store`). HNSW under continuous deletion/update degrades (KI-002).
- BM25 tuning is non-trivial on noisy forum text (stemming, stopwords, n-grams); budget ~1 week during V1 implementation.
- RRF is a "default-correct" fusion; we revisit with cross-encoder re-ranking if eval shows ranking quality issues.

## Alternatives considered

- **Qdrant sidecar (V1)** — best-in-class hybrid (sparse+dense), best filtered-ANN. Rejected for V1 because the operational cost isn't justified at our scale.
- **LanceDB embedded** — could replace BOTH the vector and FTS layers. Considered but adds a 4th storage system; not justified.
- **Cross-encoder reranking** as final stage — V1.x improvement; deferred.
- **Pure-vector retrieval (no BM25)** — fails on rare-token queries (specific school names, acronyms). BM25 catches those.

## Related docs

- `docs/03-research/research-log.md` R-002
- `docs/03-research/R-006-live-verification.md` R-002 section
- `docs/04-architecture/system-overview.md` §5 (retrieval ranking)
- `docs/04-architecture/tech-stack.md` Retrieval section

## Related code

- `src/retrieval/api.py` — `RetrievalService` / `query_graph`
- `src/retrieval/index.py` — `HybridIndex`: TF-IDF (BM25-family) + cosine kNN + RRF fusion
- `src/retrieval/ranking.py` — tier × rank × HALO decay × credibility × consistency scorer (ADR-021)
