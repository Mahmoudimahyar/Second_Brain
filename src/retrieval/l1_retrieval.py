"""ED-4: official L1 article retrieval — bring authoritative crawled prose into the
Evidence Dossier so it can say "the ADA/ADEA/CDA article at <url> says: …".

The L1 web corpus is small and process/regulatory (ada.org, adea.org, cda-adc.ca, ndeb,
coda, tmdsas, natmatch — boards, applications, accreditation, the licensure compact). So
it's the authoritative source for **process** questions; school-stat questions anchor on
L1 `Claim`/`Metric` nodes instead.

Relevance is **semantic** (cosine of the question vs precomputed chunk embeddings,
`cloud/embed_l1_chunks.py`) with a floor — keyword matching of generic English words
("lead", "process", "success") over 13,570 dense governing-body chunks finds spurious
hits and makes the dossier over-answer out-of-domain questions. A keyword path is kept
as a fallback when the chunk embeddings aren't present.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Authority prior for the governing bodies we crawled (higher = more trusted).
_DOMAIN_WEIGHT: dict[str, float] = {
    "www.ada.org": 3.0, "ada.org": 3.0, "coda.ada.org": 3.0, "jcnde.ada.org": 3.0,
    "adea.org": 3.0, "www.adea.org": 3.0, "access.adea.org": 2.5, "elearn.adea.org": 2.0,
    "programs.adea.org": 2.5, "www.cda-adc.ca": 2.5, "ndeb-bned.ca": 2.5,
    "tmdsas.com": 2.0, "www.tmdsas.com": 2.0, "natmatch.com": 2.0,
    "adextesting.org": 2.0, "aadbcompact.org": 1.5,
}
_SCHOOL_MENTION_BOOST = 4.0
# Crawled page-navigation chrome to strip from snippets.
_NAV_RE = re.compile(
    r"Skip to (?:main )?content|Menu Toggle|Skip to content|Main Menu", re.I)
# Cosine floor — BGE-small has a high similarity baseline (out-of-domain questions still
# score ~0.62-0.71 against dental chunks), so the floor sits high. Measured separation:
# out-of-domain tops ~0.71, in-domain (compact/DAT/CODA) bottoms ~0.76. 0.73 splits them.
_DEFAULT_FLOOR = 0.73


@dataclass
class L1Article:
    chunk_id: str
    page_id: str
    url: str
    title: str
    domain: str
    snippet: str
    score: float
    school_matched: bool


class L1ArticleIndex:
    """In-memory index of L1 Page/Chunk text for topic retrieval of official prose."""

    def __init__(
        self, nodes_parquet: str, edges_parquet: str, *, embedder=None, emb_dir: str | None = None,
    ) -> None:
        import duckdb  # noqa: PLC0415

        con = duckdb.connect()
        self._chunk_by_id: dict[str, tuple[str, str]] = {}  # chunk_id -> (text, page_id)
        for cid, pj in con.execute(
            f"SELECT id, properties_json FROM read_parquet('{nodes_parquet}') WHERE label='Chunk'"
        ).fetchall():
            p = json.loads(pj) if pj else {}
            txt = p.get("text", "") or ""
            if txt:
                self._chunk_by_id[cid] = (txt, p.get("page_id", ""))

        self._pages: dict[str, tuple[str, str, str]] = {}  # page_id -> (url, title, domain)
        for pid, pj in con.execute(
            f"SELECT id, properties_json FROM read_parquet('{nodes_parquet}') WHERE label='Page'"
        ).fetchall():
            p = json.loads(pj) if pj else {}
            self._pages[pid] = (p.get("url", ""), p.get("title", ""), p.get("domain", ""))

        self._mentions: dict[str, set[str]] = {}
        for frm, to in con.execute(
            f"SELECT from_id, to_id FROM read_parquet('{edges_parquet}') WHERE label='MENTIONS'"
        ).fetchall():
            self._mentions.setdefault(frm, set()).add(to)

        # Semantic index (precomputed chunk embeddings), if available.
        self._embedder = embedder
        self._chunk_ids: list[str] = []
        self._chunk_mat: np.ndarray | None = None
        if emb_dir:
            npy = Path(emb_dir) / "l1_chunks_bge.npy"
            idf = Path(emb_dir) / "l1_chunks_bge.ids.txt"
            if npy.exists() and idf.exists():
                mat = np.load(npy, mmap_mode="r")
                ids = idf.read_text(encoding="utf-8").splitlines()
                if len(ids) == mat.shape[0]:
                    self._chunk_mat = mat
                    self._chunk_ids = ids

    @property
    def size(self) -> int:
        return len(self._chunk_by_id)

    @property
    def semantic(self) -> bool:
        return self._chunk_mat is not None and self._embedder is not None

    @staticmethod
    def _snippet(text: str, match: re.Match | None, *, width: int = 260) -> str:
        if match is None:
            raw = text[:width]
        else:
            start = max(0, match.start() - width // 3)
            raw = text[start:start + width]
        # Strip crawled page-nav boilerplate ("Skip to content", "Menu Toggle", …) and
        # collapse whitespace so the snippet shows article prose, not the site chrome.
        raw = _NAV_RE.sub(" ", raw)
        return re.sub(r"\s+", " ", raw).strip()

    def _make(self, cid: str, page_id: str, text: str, score: float,
              terms_pat, sset: set[str]) -> L1Article:
        url, title, domain = self._pages.get(page_id, ("", "", ""))
        mentioned = self._mentions.get(cid, set()) | self._mentions.get(page_id, set())
        school_matched = bool(sset & mentioned)
        m = terms_pat.search(text) if terms_pat else None
        return L1Article(
            chunk_id=cid, page_id=page_id, url=url, title=title, domain=domain,
            snippet=self._snippet(text, m),
            score=score + (_SCHOOL_MENTION_BOOST * 0.05 if school_matched else 0.0)
            + _DOMAIN_WEIGHT.get(domain, 0.5) * 0.02,
            school_matched=school_matched,
        )

    def retrieve(
        self, terms: list[str], school_ids: list[str] | None = None, *,
        top_k: int = 5, query_text: str | None = None, floor: float = _DEFAULT_FLOOR,
    ) -> list[L1Article]:
        sset = set(school_ids or [])
        terms_pat = (re.compile(r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b", re.I)
                     if terms else None)

        # Semantic path (preferred): cosine of question vs chunk embeddings, floored.
        if self.semantic and query_text:
            q = self._embedder.embed_query(query_text)
            sims = np.asarray(self._chunk_mat, dtype=np.float32) @ np.asarray(q, dtype=np.float32)
            order = np.argsort(-sims)
            out: list[L1Article] = []
            for i in order:
                sim = float(sims[i])
                if sim < floor:
                    break  # sorted desc — nothing relevant remains
                cid = self._chunk_ids[i]
                tp = self._chunk_by_id.get(cid)
                if tp is None:
                    continue
                out.append(self._make(cid, tp[1], tp[0], sim, terms_pat, sset))
                if len(out) >= top_k * 3:
                    break
            out.sort(key=lambda a: -a.score)
            return out[:top_k]

        # Keyword fallback (no chunk embeddings present): word-boundary match + floor.
        if not terms_pat:
            return []
        out = []
        for cid, (txt, page_id) in self._chunk_by_id.items():
            hits = terms_pat.findall(txt)
            if not hits:
                continue
            n_hits, distinct = len(hits), len({h.lower() for h in hits})
            mentioned = self._mentions.get(cid, set()) | self._mentions.get(page_id, set())
            if not (distinct >= 2 or n_hits >= 4 or bool(sset & mentioned)):
                continue
            out.append(self._make(cid, page_id, txt, float(n_hits), terms_pat, sset))
        out.sort(key=lambda a: -a.score)
        return out[:top_k]
