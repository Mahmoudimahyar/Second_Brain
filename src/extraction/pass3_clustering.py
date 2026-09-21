"""Pass 3 semantic clustering per `plan.md`.

Embeds posts via the `EmbeddingService` Protocol, clusters with one of:
  - ``"kmeans"``         — MiniBatchKMeans on raw embeddings (default)
  - ``"hdbscan"``        — density-based, K-less clustering
  - ``"signed_spectral"``— BNC signed spectral clustering (GAP-049 / ADR-006)

Signed spectral clustering wires sentiment labels into the graph structure:
positive edges between same-sentiment similar posts; negative edges between
opposite-sentiment (positive vs negative) posts.  The signed Laplacian
eigenvectors are then clustered with KMeans, naturally surfacing stance
communities rather than pure topic communities.

Pass 3 runs on raw embeddings; sentiment labels (from Pass 4 SentimentAnnotations)
can be supplied via the ``sentiments`` kwarg on ``run()`` for a post-Pass-4
re-clustering.  When ``sentiments`` is absent or empty, signed_spectral
degrades gracefully to plain KMeans.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import Any

from src.embeddings.api import Embedding, EmbeddingService
from src.extraction.cache import ExtractionCache
from src.extraction.pass4_schemas import schema_hash
from src.gateway import strip_json_fences
from src.gateway.api import ModelGateway, TaskID
from src.graph.client import Edge, Node
from src.shared.timestamps import to_iso


@dataclass(frozen=True)
class ClusterSummary:
    cluster_id: str
    label: str                  # short topic name produced by the LLM
    description: str            # one-sentence summary
    member_count: int
    centroid: tuple[float, ...]
    member_post_ids: list[str]


@dataclass(frozen=True)
class Pass3Output:
    embeddings: list[Embedding]
    clusters: list[ClusterSummary]
    nodes: list[Node]
    edges: list[Edge]
    cost_usd: float = 0.0


@dataclass
class Pass3ClusterRunner:
    """Runs Pass 3 on a batch of (post_id, post_text) pairs.

    Two-stage:
      1. Embed all posts via `EmbeddingService` (BGE-small in production).
      2. Cluster with `MiniBatchKMeans(n_clusters=k)`. For each cluster, call
         the gateway with up to `summary_sample_size` representative posts and
         ask for a (label, description) JSON object.

    A cluster's nodes use deterministic IDs so re-running on the same sample
    is idempotent.
    """

    embedder: EmbeddingService
    gateway: ModelGateway | None = None
    cache: ExtractionCache | None = None
    n_clusters: int = 8
    summary_sample_size: int = 5
    min_cluster_size: int = 2          # clusters smaller than this are skipped
    cluster_seed: int = 42
    method: str = "kmeans"             # "kmeans" | "hdbscan" — see _cluster()
    _summary_calls: list[float] = field(default_factory=list, init=False)

    def run(
        self,
        posts: list[tuple[str, str]],
        *,
        ingest_time: datetime,
        sentiments: dict[str, str] | None = None,
    ) -> Pass3Output:
        """Run Pass-3 clustering over ``posts``.

        ``sentiments`` maps post_id → sentiment label ("positive" | "negative" |
        "neutral").  Used only when ``self.method == "signed_spectral"``; ignored
        otherwise.  When provided, signed spectral clustering separates stance
        communities; absent → falls back to plain KMeans inside the method.
        """
        if not posts:
            return Pass3Output(embeddings=[], clusters=[], nodes=[], edges=[])

        post_ids = [pid for pid, _ in posts]
        texts = [text for _, text in posts]
        embs = self.embedder.embed_batch(texts)

        cluster_assignments, centroids = self._cluster(
            embs, post_ids=post_ids, sentiments=sentiments or {})
        groups: dict[int, list[int]] = {}
        for idx, c in enumerate(cluster_assignments):
            groups.setdefault(c, []).append(idx)

        nodes: list[Node] = []
        edges: list[Edge] = []
        summaries: list[ClusterSummary] = []
        total_cost = 0.0
        ingest_iso = to_iso(ingest_time)

        for cluster_idx, member_indices in groups.items():
            if cluster_idx < 0:    # HDBSCAN noise / unassigned
                continue
            if len(member_indices) < self.min_cluster_size:
                continue
            sample_texts = [texts[i] for i in member_indices[: self.summary_sample_size]]
            sample_post_ids = [post_ids[i] for i in member_indices]
            centroid = tuple(float(v) for v in centroids[cluster_idx])
            label, description, cost = self._summarize_cluster(sample_texts, centroid=centroid)
            total_cost += cost
            cluster_node_id = self._cluster_id(centroid, label)
            summary = ClusterSummary(
                cluster_id=cluster_node_id,
                label=label,
                description=description,
                member_count=len(member_indices),
                centroid=centroid,
                member_post_ids=sample_post_ids,
            )
            summaries.append(summary)
            nodes.append(Node(
                id=cluster_node_id, label="Cluster", source_tier="L5",
                properties={
                    "topic_label": label, "description": description,
                    "member_count": len(member_indices),
                    "embedding_model": self.embedder.model,
                    "ingest_iso": ingest_iso,
                },
            ))
            for member_idx in member_indices:
                edges.append(Edge(
                    id=f"edge:in_cluster:{post_ids[member_idx]}:{cluster_node_id}",
                    label="IN_CLUSTER",
                    from_id=post_ids[member_idx], to_id=cluster_node_id,
                    source_tier="L5", rank="normal",
                    references=[post_ids[member_idx]],
                    t_valid_from=ingest_time, t_ingest_from=ingest_time,
                ))

        return Pass3Output(
            embeddings=embs, clusters=summaries,
            nodes=nodes, edges=edges, cost_usd=total_cost,
        )

    def _cluster(
        self,
        embs: list[Embedding],
        *,
        post_ids: list[str] | None = None,
        sentiments: dict[str, str] | None = None,
    ) -> tuple[list[int], list[tuple[float, ...]]]:
        n_posts = len(embs)
        if n_posts == 0:
            return [], []
        if self.method not in {"kmeans", "hdbscan", "signed_spectral"}:
            raise ValueError(
                f"unknown clustering method: {self.method!r} "
                "(expected 'kmeans', 'hdbscan', or 'signed_spectral')",
            )
        if self.method == "hdbscan":
            return self._cluster_hdbscan(embs)
        if self.method == "signed_spectral":
            return self._cluster_signed_spectral(
                embs, post_ids=post_ids or [], sentiments=sentiments or {})
        return self._cluster_kmeans(embs)

    def _cluster_kmeans(
        self, embs: list[Embedding],
    ) -> tuple[list[int], list[tuple[float, ...]]]:
        n_posts = len(embs)
        k = min(self.n_clusters, n_posts)
        if k == 1:
            return [0] * n_posts, [tuple(embs[0].vector)]
        try:
            import numpy as np  # noqa: PLC0415
            from sklearn.cluster import MiniBatchKMeans  # noqa: PLC0415
        except ImportError as e:  # pragma: no cover
            raise ImportError(
                "Pass3ClusterRunner needs scikit-learn + numpy. "
                "Install with `pip install scikit-learn`.",
            ) from e
        matrix = np.asarray([e.vector for e in embs], dtype=np.float32)
        model = MiniBatchKMeans(
            n_clusters=k, random_state=self.cluster_seed,
            n_init=3, batch_size=min(32, n_posts),
        )
        labels = model.fit_predict(matrix)
        centroids = [
            tuple(float(v) for v in row) for row in model.cluster_centers_
        ]
        return [int(label) for label in labels], centroids

    def _cluster_hdbscan(
        self, embs: list[Embedding],
    ) -> tuple[list[int], list[tuple[float, ...]]]:
        """Density-based, K-less alternative — closer to A-055's spirit than
        MiniBatchKMeans. Outliers go to cluster -1; we then compute centroids
        from member embeddings (HDBSCAN has no native cluster_centers_).

        Caveat: the *full* A-055 spec wants signed-graph community detection
        on SUPPORTS / CONTRADICTS edges from Pass 4. Those edges don't exist
        at Pass 3 (the dependency runs the other way). HDBSCAN is the V1.x
        step-up; the true signed-graph version is a V2 follow-up.
        """

        try:
            import numpy as np  # noqa: PLC0415
            from sklearn.cluster import HDBSCAN  # noqa: PLC0415
        except ImportError as e:  # pragma: no cover
            raise ImportError(
                "Pass3ClusterRunner(method='hdbscan') needs scikit-learn>=1.3.",
            ) from e
        matrix = np.asarray([e.vector for e in embs], dtype=np.float32)
        model = HDBSCAN(
            min_cluster_size=max(self.min_cluster_size, 2),
            metric="euclidean",
        )
        raw_labels = model.fit_predict(matrix)
        labels = [int(v) for v in raw_labels]
        unique = sorted({label for label in labels if label >= 0})
        centroids: list[tuple[float, ...]] = []
        for cluster_idx in unique:
            members = [
                matrix[i] for i, label in enumerate(labels) if label == cluster_idx
            ]
            if not members:
                continue
            centroid = np.mean(np.vstack(members), axis=0)
            centroids.append(tuple(float(v) for v in centroid))
        # Remap labels to contiguous 0..N-1 in `unique` order; -1 stays as -1
        # (caller's min_cluster_size guard will skip it).
        remap = {cluster_idx: new_idx for new_idx, cluster_idx in enumerate(unique)}
        new_labels = [remap.get(label, -1) for label in labels]
        return new_labels, centroids

    def _cluster_signed_spectral(
        self,
        embs: list[Embedding],
        *,
        post_ids: list[str],
        sentiments: dict[str, str],
    ) -> tuple[list[int], list[tuple[float, ...]]]:
        """BNC-style signed spectral clustering (GAP-049 / ADR-006).

        Builds a signed cosine-similarity matrix:
          A_ij = +cos(i,j)  if both posts share the same non-neutral sentiment
          A_ij = -cos(i,j)  if posts hold opposite sentiments (positive vs negative)
          A_ij =  0         when either post has neutral/unknown sentiment

        The signed Laplacian L = D_|A| - A (where D_|A| has row sums of |A| on
        the diagonal) is factorised with scipy; the k smallest eigenvectors form
        a k-dimensional stance embedding that KMeans then clusters.

        Falls back to plain KMeans when:
          - scipy is unavailable
          - no sentiment labels are provided for any post
          - the matrix is numerically degenerate
        """
        n = len(embs)
        k = min(self.n_clusters, n)
        if k == 1:
            return [0] * n, [tuple(embs[0].vector)]

        try:
            import numpy as np                       # noqa: PLC0415
            from scipy.linalg import eigh            # noqa: PLC0415
            from sklearn.cluster import MiniBatchKMeans  # noqa: PLC0415
            from sklearn.preprocessing import normalize  # noqa: PLC0415
        except ImportError:
            return self._cluster_kmeans(embs)

        matrix = np.asarray([e.vector for e in embs], dtype=np.float32)
        matrix_norm = normalize(matrix, norm="l2")    # unit rows → cosine = dot
        S = (matrix_norm @ matrix_norm.T).astype(np.float32)   # (n, n)

        # Per-post sentiment label arrays
        sents = np.array([sentiments.get(pid, "neutral") for pid in post_ids])
        is_pos = sents == "positive"
        is_neg = sents == "negative"
        is_opinion = is_pos | is_neg

        # If no posts have opinion labels, signed structure is empty → KMeans fallback
        if not is_opinion.any():
            return self._cluster_kmeans(embs)

        # Vectorised signed adjacency:
        #   same-opinion pairs  → positive edge (+S_ij)
        #   opposite-opinion    → negative edge (-S_ij)
        #   neutral-touching    → no edge (0)
        same_mask = np.outer(is_pos, is_pos) | np.outer(is_neg, is_neg)
        opp_mask  = np.outer(is_pos, is_neg) | np.outer(is_neg, is_pos)
        A = np.where(same_mask, S, np.where(opp_mask, -S, 0.0)).astype(np.float32)

        # Signed Laplacian  L = D_|A| - A
        abs_row_sums = np.abs(A).sum(axis=1)
        L = np.diag(abs_row_sums) - A

        # k smallest eigenvectors of symmetric L (numerically stable via eigh)
        try:
            upper = min(k, n) - 1
            _, vecs = eigh(L.astype(np.float64), subset_by_index=[0, upper])
            eigvecs = vecs.astype(np.float32)   # (n, k)
        except Exception:  # noqa: BLE001 — degenerate matrix
            return self._cluster_kmeans(embs)

        # KMeans on the k-dim signed-Laplacian embedding
        km = MiniBatchKMeans(
            n_clusters=k, random_state=self.cluster_seed,
            n_init=3, batch_size=min(32, n),
        )
        labels = [int(v) for v in km.fit_predict(eigvecs)]

        # Centroids in the ORIGINAL embedding space (for stable cluster IDs)
        centroids: list[tuple[float, ...]] = []
        for c in range(k):
            members = [matrix[i] for i, lbl in enumerate(labels) if lbl == c]
            if members:
                centroid = np.mean(np.vstack(members), axis=0)
            else:
                centroid = matrix[0]
            centroids.append(tuple(float(v) for v in centroid))

        return labels, centroids

    def _summarize_cluster(
        self, sample_texts: list[str],
        *,
        centroid: tuple[float, ...] = (),
    ) -> tuple[str, str, float]:
        if self.gateway is None:
            # No LLM — fall back to a deterministic label from the first post.
            label = (sample_texts[0][:32] or "cluster") if sample_texts else "cluster"
            return label, "(no LLM gateway configured)", 0.0
        cache_key = self._cache_key_for_cluster(centroid, sample_texts)
        if self.cache is not None:
            cached = self.cache.get(cache_key)
            if cached is not None:
                try:
                    cached_obj = json.loads(cached.output_json)
                    return (
                        str(cached_obj.get("label") or "cluster")[:64],
                        str(cached_obj.get("description") or "")[:280],
                        0.0,                   # cache hit — no cost re-billed
                    )
                except json.JSONDecodeError:
                    pass                       # corrupt cache row → refetch
        prompt = _build_cluster_prompt(sample_texts)
        try:
            resp = self.gateway.complete(
                TaskID.PASS3_CLUSTER_SUMMARY, prompt, schema=None,
            )
        except RuntimeError:
            return "cluster", "(no gateway provider for PASS3_CLUSTER_SUMMARY)", 0.0
        text = strip_json_fences(resp.raw_text)
        try:
            parsed = json.loads(text)
            label = str(parsed.get("label") or "cluster")[:64]
            description = str(parsed.get("description") or "")[:280]
        except json.JSONDecodeError:
            label, description = "cluster", text[:280]
        if self.cache is not None:
            self.cache.put_output(
                cache_key,
                {"label": label, "description": description},
                vendor=resp.vendor, model=resp.model,
                input_tokens=resp.input_tokens, output_tokens=resp.output_tokens,
                cost_usd=float(resp.cost_usd),
            )
        return label, description, float(resp.cost_usd)

    @staticmethod
    def _cache_key_for_cluster(
        centroid: tuple[float, ...], sample_texts: list[str],
    ) -> str:
        """GAP-039: deterministic label cache keyed on the centroid signature +
        sorted sample texts. Same input across re-runs → same `label`."""

        h = sha256()
        for v in centroid[:16]:
            h.update(f"{v:.4f}|".encode("ascii"))
        for sample in sorted(sample_texts):
            h.update(sample.encode("utf-8"))
            h.update(b"|")
        return f"cache:pass3_cluster:{h.hexdigest()[:32]}"

    def _cluster_id(
        self, centroid: tuple[float, ...], label: str,
    ) -> str:
        # Stable ID = hash of (first 8 centroid dims + label slug)
        from hashlib import sha256  # noqa: PLC0415
        h = sha256()
        for v in centroid[:8]:
            h.update(f"{v:.6f}|".encode("ascii"))
        h.update(label.lower().encode("utf-8"))
        return f"cluster:{h.hexdigest()[:16]}"


_PASS3_PROMPT = """\
You are clustering dental-school applicant forum posts by topic.

Below are %d posts from one cluster. Produce a SHORT topic label (2-5 words)
and a one-sentence description of what the posts have in common.

Output STRICT JSON, no prose:
{
  "label": "short topic label",
  "description": "one-sentence description"
}

POSTS:
%s
"""


def _build_cluster_prompt(samples: list[str]) -> str:
    joined = "\n---\n".join(s[:400] for s in samples)
    return _PASS3_PROMPT % (len(samples), joined)


# Reference the schema_hash import so it's available for callers that want to
# extend Pass 3 with content-addressable caching.
_ = schema_hash


def _maybe_use(_: Any) -> None:  # pragma: no cover
    pass
