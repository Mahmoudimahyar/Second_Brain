"""RP-2: per-document enrichment — the dimensions the protocol slices and de-biases on.

- TIME (real): year from `created_iso` (reddit ~96% coverage, 2010-2026).
- COHORT (proxy): subreddit from the URL — r/predental = applicants, r/DentalSchool =
  students, r/Dentistry = professionals. A comment inherits its parent post's subreddit.
- AUTHOR: for unique-author denominators (kills one-loud-user volume skew).
- PRICE (proxy): dollar amounts extracted from text for willingness-to-pay questions.

Cohort/price are transparent proxies, not gold; every dossier labels them as such.
"""

from __future__ import annotations

import re
import sqlite3

_SUBREDDIT_RE = re.compile(r"/r/([^/]+)/", re.I)
_COHORT = {
    "predental": "pre-dental applicant",
    "predentalschool": "pre-dental applicant",
    "dentalschool": "dental student",
    "dentistry": "practicing/professional",
    "dentalhygiene": "hygiene",
}
# $1,500 / $300 / $2k / $1.5k  (avoids bare years; requires a $ sign). Single-digit
# amounts are allowed only so "$2k" parses; the lo floor drops bare "$5".
_PRICE_RE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d{1,6})(?:\.(\d{1,2}))?\s?([kK])?")


_JUNK_PREFIX = ("this post", "your post", "your submission", "your comment", "please use",
                "i am a bot", "this comment was removed", "this action was performed",
                "thank you for your submission", "removed", "deleted",
                "any pre-dental", "all pre-dental", "questions should be directed",
                "this is an automated", "all questions about", "welcome to r/")


def is_junk(text: str | None, author: str | None) -> bool:
    """Automod / removed / deleted / empty-ish content that shouldn't form a topic."""
    if author == "AutoModerator":
        return True
    t = (text or "").strip().lower()
    if len(t) < 15 or t in ("[removed]", "[deleted]"):
        return True
    return t.startswith(_JUNK_PREFIX)


def year_of(created_iso: str | None) -> int | None:
    if created_iso and len(created_iso) >= 4 and created_iso[:4].isdigit():
        y = int(created_iso[:4])
        return y if 2000 <= y <= 2030 else None
    return None


def subreddit_of(url: str | None) -> str | None:
    if not url:
        return None
    m = _SUBREDDIT_RE.search(url)
    return m.group(1) if m else None


def cohort_of(subreddit: str | None) -> str:
    if not subreddit:
        return "unknown"
    return _COHORT.get(subreddit.lower(), f"r/{subreddit}")


def extract_prices(text: str, *, lo: float = 20.0, hi: float = 100_000.0) -> list[float]:
    """Dollar amounts in a plausible advising/service range (excludes cents-only, keeps
    $X / $X,XXX / $Xk). The caller restricts `text` to the relevant context."""
    out: list[float] = []
    for m in _PRICE_RE.finditer(text or ""):
        val = float(m.group(1).replace(",", ""))
        if m.group(3):                      # trailing k
            val *= 1000
        if lo <= val <= hi:
            out.append(val)
    return out


def enrich_items(docs_conn: sqlite3.Connection, id_to_bucket: dict[str, str]) -> list[dict]:
    """{doc_id -> bucket} -> [{doc_id, bucket, thread_id, author, year, cohort, score}].

    Resolves each doc's metadata from documents.sqlite; a comment's cohort is inherited
    from its parent post's subreddit (comments carry no URL of their own).
    """
    ids = list(id_to_bucket)
    if not ids:
        return []
    rows: list[tuple] = []
    for i in range(0, len(ids), 400):
        batch = ids[i:i + 400]
        marks = ",".join("?" * len(batch))
        rows.extend(docs_conn.execute(
            f"SELECT doc_id, doc_type, thread_id, author, created_iso, score, url "  # noqa: S608
            f"FROM documents WHERE doc_id IN ({marks})", batch).fetchall())
    # parent-post subreddit for comments lacking their own URL
    need = sorted({r[2] for r in rows if not r[6] and r[0].startswith("reddit_comment:") and r[2]})
    posturl: dict[str, str] = {}
    for i in range(0, len(need), 400):
        batch = need[i:i + 400]
        marks = ",".join("?" * len(batch))
        for d, u in docs_conn.execute(
            f"SELECT doc_id, url FROM documents WHERE doc_id IN ({marks})", batch):  # noqa: S608
            if u:
                posturl[d] = u
    items: list[dict] = []
    for doc_id, _dt, thread_id, author, created_iso, score, url in rows:
        sub = subreddit_of(url) or subreddit_of(posturl.get(thread_id))
        cohort = cohort_of(sub) if doc_id.startswith("reddit") else "sdn"
        a = author if author and author not in ("[deleted]", "") else None
        items.append({
            "doc_id": doc_id, "bucket": id_to_bucket[doc_id], "thread_id": thread_id or doc_id,
            "author": a, "year": year_of(created_iso),
            "cohort": cohort, "score": score or 0,
        })
    return items


def clusters_for(items: list[dict], bucket: str) -> list[list[int]]:
    """Thread-grouped 0/1 indicators of membership in `bucket` (input to the cluster
    bootstrap). One inner list per thread."""
    by_thread: dict[str, list[int]] = {}
    for it in items:
        by_thread.setdefault(it["thread_id"], []).append(1 if it["bucket"] == bucket else 0)
    return list(by_thread.values())
