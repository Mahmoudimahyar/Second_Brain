"""Evidence census — broad-recall population counts for the Evidence Dossier.

Decision (2026-06-18, `project_evidence_dossier`): **broad-then-filter**. This module
does the BROAD step — count how many forum/SDN documents *match* a question, partitioned
by source type — so an answer can open with the honest headline:

    "210 reddit posts, 1,100 reddit comments and 2 SDN posts relate to your question."

This is the **population** count, deliberately distinct from the **display** set (the top-k
exemplars the engine actually shows). The relevance filter (similarity floor, junk removal)
runs downstream on the pulled candidates — this census is the wide net before that prune.

Official L1 article counts (CDA/ADA/ADEA) are NOT here: those documents live in the graph
as Page/Chunk nodes, not in `documents.sqlite`. `KBAgent` adds them separately.

`documents.sqlite` schema (verified 2026-06-18): no `source_tier` column — tier is derived
from `doc_type` via `DOC_TYPE_TIER`.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

# doc_type -> tier. All forum/SDN docs are L5; official articles (L1) are in the graph.
DOC_TYPE_TIER: dict[str, str] = {
    "reddit_post": "L5",
    "reddit_comment": "L5",
    "sdn_post": "L5",
}

# Tiny stopword set — we only need to strip terms that would match almost everything
# and make the "broad" net meaninglessly wide. Domain words (school, dental) are kept;
# the downstream relevance filter, not the census, is responsible for precision.
_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "at", "is", "are",
    "was", "were", "be", "been", "do", "does", "did", "how", "what", "which", "who",
    "whom", "this", "that", "these", "those", "with", "as", "by", "from", "about",
    "into", "than", "then", "i", "you", "it", "my", "me", "we", "they", "should",
    "would", "could", "can", "will", "if", "any", "all", "get", "getting", "vs",
})


def build_fts_query(question: str) -> str:
    """Build a broad FTS5 MATCH expression: content terms joined with OR.

    OR (not the FTS5 implicit AND) is the whole point — we want recall. Each term is
    double-quoted so punctuation/reserved tokens can't break the query. Returns "" when
    the question has no usable content terms (caller should skip the FTS path).
    """
    terms = [
        t for t in re.findall(r"[a-z0-9]+", question.lower())
        if t not in _STOPWORDS and len(t) > 2
    ]
    # De-dupe, preserve order.
    seen: set[str] = set()
    uniq = [t for t in terms if not (t in seen or seen.add(t))]
    return " OR ".join(f'"{t}"' for t in uniq)


@dataclass
class CensusResult:
    """Broad population counts for one question (forum/SDN only)."""

    fts_query: str
    counts_by_type: dict[str, int] = field(default_factory=dict)  # doc_type -> n
    counts_by_tier: dict[str, int] = field(default_factory=dict)  # tier -> n
    total: int = 0

    def to_dict(self) -> dict:
        return {
            "fts_query": self.fts_query,
            "counts_by_type": self.counts_by_type,
            "counts_by_tier": self.counts_by_tier,
            "total": self.total,
        }


def _has_fts5(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='docs_fts'"
    ).fetchone()
    return row is not None


def forum_census(conn: sqlite3.Connection, question: str) -> CensusResult:
    """Count forum/SDN documents matching `question`, grouped by doc_type.

    Uses FTS5 broad OR-match when available, else a LIKE scan on the first content term
    (slower, narrower — FTS5 is expected in production).
    """
    fts = build_fts_query(question)
    counts: dict[str, int] = {}

    if _has_fts5(conn) and fts:
        rows = conn.execute(
            "SELECT d.doc_type, count(*) "
            "FROM docs_fts f JOIN documents d ON f.rowid = d.rowid "
            "WHERE docs_fts MATCH ? "
            "GROUP BY d.doc_type",
            (fts,),
        ).fetchall()
    else:
        # LIKE fallback: broadest single term we have.
        terms = [t for t in re.findall(r"[a-z0-9]+", question.lower())
                 if t not in _STOPWORDS and len(t) > 2]
        if not terms:
            return CensusResult(fts_query="")
        like = f"%{terms[0]}%"
        rows = conn.execute(
            "SELECT doc_type, count(*) FROM documents WHERE text LIKE ? GROUP BY doc_type",
            (like,),
        ).fetchall()

    by_tier: dict[str, int] = {}
    for doc_type, n in rows:
        counts[doc_type] = counts.get(doc_type, 0) + int(n)
        tier = DOC_TYPE_TIER.get(doc_type, "L5")
        by_tier[tier] = by_tier.get(tier, 0) + int(n)

    return CensusResult(
        fts_query=fts,
        counts_by_type=counts,
        counts_by_tier=by_tier,
        total=sum(counts.values()),
    )
