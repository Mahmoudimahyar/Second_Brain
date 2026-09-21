"""Persisted semantic search over post and comment embeddings.

Loads float32 shards produced by `cloud/embed_posts.py` and
`cloud/embed_comments.py`:

  <data_dir>/embeddings/posts_bge.NNN.npy    + .ids.txt  → post search
  <data_dir>/embeddings/comments_bge.NNN.npy + .ids.txt  → comment search

Snippet text (PV-3): hydrated from `<data_dir>/raw/documents.sqlite` (the thread-
complete corpus that always ships in the bundle), keyed by the same `doc_id` the shards
use. The legacy `post_text.db` / `comment_text.db` sidecars are an optional fallback;
their absence previously left snippets empty and forced spurious abstentions (#30).

Vectors are L2-normalised at write time; cosine similarity = dot product.
877K posts × 384 fp32 ≈ 1.3 GB; a full sweep is ~100-300 ms on CPU.
Comment shards add ~3 GB when present; search path is identical.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from src.retrieval.rendering import best_sentence


@dataclass
class SemanticHit:
    doc_id: str
    score: float
    snippet: str


class SemanticIndex:
    def __init__(self, data_dir: Path | str, *, embedder=None) -> None:
        base = Path(data_dir)
        emb_dir = base / "embeddings"

        self._post_shards: list[tuple[np.ndarray, list[str]]] = []
        self._comment_shards: list[tuple[np.ndarray, list[str]]] = []

        for vec_path in sorted(emb_dir.glob("posts_bge.*.npy")):
            ids_path = Path(str(vec_path)[: -len(".npy")] + ".ids.txt")
            if not ids_path.exists():
                continue
            vecs = np.load(vec_path, mmap_mode="r")
            ids = ids_path.read_text(encoding="utf-8").splitlines()
            if len(ids) == vecs.shape[0]:
                self._post_shards.append((vecs, ids))

        for vec_path in sorted(emb_dir.glob("comments_bge.*.npy")):
            ids_path = Path(str(vec_path)[: -len(".npy")] + ".ids.txt")
            if not ids_path.exists():
                continue
            vecs = np.load(vec_path, mmap_mode="r")
            ids = ids_path.read_text(encoding="utf-8").splitlines()
            if len(ids) == vecs.shape[0]:
                self._comment_shards.append((vecs, ids))

        # PV-3: primary snippet source is the thread-complete corpus; sidecars optional.
        self._docs_db = next(
            (p for p in (base / "raw" / "documents.sqlite", base / "documents.sqlite")
             if p.exists()), None)
        self._text_db = base / "post_text.db"
        self._comment_text_db = base / "comment_text.db"
        self._embedder = embedder

    @property
    def size(self) -> int:
        return sum(v.shape[0] for v, _ in self._post_shards)

    @property
    def comment_size(self) -> int:
        return sum(v.shape[0] for v, _ in self._comment_shards)

    def _embed_query(self, query: str) -> np.ndarray:
        if self._embedder is None:
            from src.embeddings.bge_embedder import BGEEmbeddingService  # noqa: PLC0415

            self._embedder = BGEEmbeddingService(device="cpu")
        v = np.array(self._embedder.embed_batch([query])[0].vector, dtype=np.float32)
        return v / max(float(np.linalg.norm(v)), 1e-9)

    def _sidecar(self, doc_ids: list[str], db_path: Path, id_col: str) -> dict[str, str]:
        if not db_path.exists():
            return {}
        conn = sqlite3.connect(db_path)
        try:
            table = "post_text" if id_col == "post_id" else "comment_text"
            marks = ",".join("?" * len(doc_ids))
            rows = conn.execute(
                f"SELECT {id_col}, substr(text, 1, 1000) "  # noqa: S608
                f"FROM {table} WHERE {id_col} IN ({marks})", doc_ids,
            ).fetchall()
            return dict(rows)
        except sqlite3.Error:
            return {}
        finally:
            conn.close()

    def _text_map(self, doc_ids: list[str]) -> dict[str, str]:
        """doc_id -> text. Prefers documents.sqlite (always present); falls back to the
        legacy post_text / comment_text sidecars."""
        if not doc_ids:
            return {}
        if self._docs_db is not None:
            conn = sqlite3.connect(self._docs_db)
            try:
                marks = ",".join("?" * len(doc_ids))
                rows = conn.execute(
                    f"SELECT doc_id, substr(text, 1, 1000) "  # noqa: S608
                    f"FROM documents WHERE doc_id IN ({marks})", doc_ids,
                ).fetchall()
                if rows:
                    return dict(rows)
            except sqlite3.Error:
                pass
            finally:
                conn.close()
        out = self._sidecar(doc_ids, self._text_db, "post_id")
        out.update(self._sidecar(doc_ids, self._comment_text_db, "doc_id"))
        return out

    def _top_k_from_shards(
        self,
        shards: list[tuple[np.ndarray, list[str]]],
        q: np.ndarray,
        top_k: int,
    ) -> tuple[list[float], list[str]]:
        best_scores: list[float] = []
        best_ids: list[str] = []
        for vecs, ids in shards:
            scores = vecs @ q
            k = min(top_k, scores.shape[0])
            idx = np.argpartition(-scores, k - 1)[:k]
            best_scores.extend(float(scores[i]) for i in idx)
            best_ids.extend(ids[i] for i in idx)
        order = np.argsort(-np.array(best_scores))[:top_k]
        return [best_scores[i] for i in order], [best_ids[i] for i in order]

    def _hits(self, query: str, hit_ids: list[str], scores: list[float]) -> list[SemanticHit]:
        text_map = self._text_map(hit_ids)
        return [SemanticHit(doc_id=hit_ids[i], score=scores[i],
                            snippet=best_sentence(query, text_map.get(hit_ids[i], "")))
                for i in range(len(hit_ids))]

    def search(self, query: str, *, top_k: int = 8) -> list[SemanticHit]:
        """Semantic search over post shards (query-aware extractive snippets)."""
        if not self._post_shards:
            return []
        q = self._embed_query(query)
        scores, hit_ids = self._top_k_from_shards(self._post_shards, q, top_k)
        return self._hits(query, hit_ids, scores)

    def search_comments(self, query: str, *, top_k: int = 8) -> list[SemanticHit]:
        """Semantic search over comment shards (empty when shards not yet built)."""
        if not self._comment_shards:
            return []
        q = self._embed_query(query)
        scores, hit_ids = self._top_k_from_shards(self._comment_shards, q, top_k)
        return self._hits(query, hit_ids, scores)
