from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import orjson

from src.shared.timestamps import from_unix_epoch

DELETED_AUTHORS: frozenset[str] = frozenset({"[deleted]", "[removed]", ""})

# Default topic filter for broader subreddits (KI-006). Keeps dental-school
# admissions-adjacent posts in r/dentistry. Configurable via CLI / API.
DEFAULT_ADMISSIONS_KEYWORDS: tuple[str, ...] = (
    "dental school", "dental schools", "predental", "pre-dental", "pre dental",
    "DAT", "AADSAS", "acceptance", "applicant", "applying", "application",
    "interview", "waitlist", "decision day", "rolling admission", "admissions",
    "cycle", "tuition", "GPA", "personal statement", "PS draft", "letters of rec",
    "shadowing hours", "letter of recommendation",
)


def _matches_any_keyword(text: str, keywords_lower: list[str]) -> bool:
    """Module-level helper to avoid bound-method indirection in hot loops."""

    haystack = text.lower()
    return any(kw in haystack for kw in keywords_lower)


@dataclass(frozen=True)
class RedditPost:
    post_id: str
    raw_id: str
    subreddit: str
    author_user_id: str | None
    raw_author: str | None
    title: str
    selftext: str
    created_utc: datetime
    score: int | None
    ups: int | None
    downs: int | None
    num_comments: int | None
    link_flair_text: str | None
    permalink: str | None
    url: str | None
    over_18: bool


@dataclass(frozen=True)
class RedditComment:
    comment_id: str
    raw_id: str
    subreddit: str
    post_id: str
    parent_id: str
    author_user_id: str | None
    raw_author: str | None
    body: str
    created_utc: datetime
    score: int | None
    ups: int | None
    downs: int | None
    controversiality: int | None


@dataclass(frozen=True)
class RedditUser:
    user_id: str
    username: str
    subreddit: str
    first_seen_utc: datetime


@dataclass(frozen=True)
class L5RedditResult:
    subreddit: str
    posts: list[RedditPost]
    comments: list[RedditComment]
    users: list[RedditUser]


class L5RedditAdapter:
    """Adapter for Reddit JSONL dumps (Pushshift/Arctic-Shift schema).

    Implements FR-1.3 (thread reconstruction via link_id/parent_id, Unix-epoch
    normalization, canonical Post/Comment/User emission) and FR-1.5 (author
    namespacing `reddit:<sub>:<author>`).

    The adapter is a pure transformer: it reads JSONL and returns canonical
    dataclasses. Persistence is the caller's responsibility (graph store in
    Pass 1, not SQLite — L5 data is graph-resident per `data.md`).
    """

    source_tier = "L5"

    def parse(
        self,
        posts_path: Path,
        comments_path: Path | None = None,
        *,
        keyword_filter: list[str] | None = None,
    ) -> L5RedditResult:
        """Read posts (+ optional comments) JSONL and return canonical records.

        Args:
          posts_path: Reddit posts JSONL.
          comments_path: optional comments JSONL.
          keyword_filter: KI-006 topic filter for broader subreddits (e.g.
            r/dentistry). When set, a post is kept iff its title+selftext
            (case-insensitive) contains AT LEAST ONE of the keywords.
            Comments attached to dropped posts are also dropped.
        """

        posts_path = Path(posts_path)
        if not posts_path.is_file():
            raise FileNotFoundError(f"Reddit posts file not found: {posts_path}")

        subreddit = self._infer_subreddit_from_filename(posts_path.name)
        kw_lower = [k.lower() for k in (keyword_filter or [])]

        posts: list[RedditPost] = []
        kept_post_ids: set[str] = set()
        user_first_seen: dict[str, tuple[str, datetime]] = {}
        for raw in self._iter_jsonl(posts_path):
            normalized = self._normalize_post(raw, subreddit=subreddit)
            if normalized is None:
                continue
            if kw_lower and not _matches_any_keyword(
                f"{normalized.title}\n{normalized.selftext}", kw_lower,
            ):
                continue
            posts.append(normalized)
            kept_post_ids.add(normalized.post_id)
            self._record_user_first_seen(
                user_first_seen,
                user_id=normalized.author_user_id,
                username=normalized.raw_author,
                ts=normalized.created_utc,
            )

        comments: list[RedditComment] = []
        if comments_path is not None and Path(comments_path).is_file():
            for raw in self._iter_jsonl(Path(comments_path)):
                normalized_c = self._normalize_comment(raw, subreddit=subreddit)
                if normalized_c is None:
                    continue
                # When a keyword filter is active, drop comments whose root
                # post was filtered out.
                if kw_lower and normalized_c.post_id not in kept_post_ids:
                    continue
                comments.append(normalized_c)
                self._record_user_first_seen(
                    user_first_seen,
                    user_id=normalized_c.author_user_id,
                    username=normalized_c.raw_author,
                    ts=normalized_c.created_utc,
                )

        users = [
            RedditUser(
                user_id=user_id,
                username=username,
                subreddit=subreddit,
                first_seen_utc=ts,
            )
            for user_id, (username, ts) in sorted(user_first_seen.items())
        ]
        return L5RedditResult(
            subreddit=subreddit, posts=posts, comments=comments, users=users,
        )

    @staticmethod
    def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
        with path.open("rb") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    obj = orjson.loads(line)
                except orjson.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    yield obj

    @classmethod
    def _normalize_post(cls, raw: dict[str, Any], *, subreddit: str) -> RedditPost | None:
        raw_id = cls._str_or_none(raw.get("id"))
        if not raw_id:
            return None
        created = cls._created_utc(raw)
        if created is None:
            return None
        raw_author = cls._author_or_none(raw.get("author"))
        author_user_id = (
            f"reddit:{subreddit}:{raw_author}" if raw_author is not None else None
        )
        return RedditPost(
            post_id=f"reddit_post:{raw_id}",
            raw_id=raw_id,
            subreddit=subreddit,
            author_user_id=author_user_id,
            raw_author=raw_author,
            title=str(raw.get("title") or ""),
            selftext=str(raw.get("selftext") or ""),
            created_utc=created,
            score=cls._int_or_none(raw.get("score")),
            ups=cls._int_or_none(raw.get("ups")),
            downs=cls._int_or_none(raw.get("downs")),
            num_comments=cls._int_or_none(raw.get("num_comments")),
            link_flair_text=cls._str_or_none(raw.get("link_flair_text")),
            permalink=cls._str_or_none(raw.get("permalink")),
            url=cls._str_or_none(raw.get("url")),
            over_18=bool(raw.get("over_18", False)),
        )

    @classmethod
    def _normalize_comment(
        cls, raw: dict[str, Any], *, subreddit: str,
    ) -> RedditComment | None:
        raw_id = cls._str_or_none(raw.get("id"))
        if not raw_id:
            return None
        link_id = cls._str_or_none(raw.get("link_id"))
        if not link_id:
            return None  # orphan comment without a root post reference
        parent_id = cls._str_or_none(raw.get("parent_id")) or link_id
        created = cls._created_utc(raw)
        if created is None:
            return None
        raw_author = cls._author_or_none(raw.get("author"))
        author_user_id = (
            f"reddit:{subreddit}:{raw_author}" if raw_author is not None else None
        )
        return RedditComment(
            comment_id=f"reddit_comment:{raw_id}",
            raw_id=raw_id,
            subreddit=subreddit,
            post_id=cls._canonicalize_thing(link_id),
            parent_id=cls._canonicalize_thing(parent_id),
            author_user_id=author_user_id,
            raw_author=raw_author,
            body=str(raw.get("body") or ""),
            created_utc=created,
            score=cls._int_or_none(raw.get("score")),
            ups=cls._int_or_none(raw.get("ups")),
            downs=cls._int_or_none(raw.get("downs")),
            controversiality=cls._int_or_none(raw.get("controversiality")),
        )

    @staticmethod
    def _canonicalize_thing(thing: str) -> str:
        """`t3_<id>` → `reddit_post:<id>`; `t1_<id>` → `reddit_comment:<id>`. Falls through unchanged otherwise."""

        if thing.startswith("t3_"):
            return f"reddit_post:{thing[3:]}"
        if thing.startswith("t1_"):
            return f"reddit_comment:{thing[3:]}"
        return thing

    @staticmethod
    def _author_or_none(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if text in DELETED_AUTHORS:
            return None
        return text

    @staticmethod
    def _str_or_none(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _int_or_none(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    @classmethod
    def _created_utc(cls, raw: dict[str, Any]) -> datetime | None:
        ts = raw.get("created_utc")
        if ts is None:
            ts = raw.get("created")
        if ts is None:
            return None
        try:
            return from_unix_epoch(ts)
        except (ValueError, OverflowError, TypeError):
            return None

    @staticmethod
    def _record_user_first_seen(
        seen: dict[str, tuple[str, datetime]],
        *,
        user_id: str | None,
        username: str | None,
        ts: datetime,
    ) -> None:
        if user_id is None or username is None:
            return
        prior = seen.get(user_id)
        if prior is None or ts < prior[1]:
            seen[user_id] = (username, ts)

    @staticmethod
    def _matches_any_keyword(text: str, keywords_lower: list[str]) -> bool:
        haystack = text.lower()
        return any(kw in haystack for kw in keywords_lower)

    @staticmethod
    def _infer_subreddit_from_filename(name: str) -> str:
        """`r_DentalSchool_posts.jsonl` → `DentalSchool`; `r_predental_*.jsonl` → `predental`."""

        stem = Path(name).stem
        if stem.startswith("r_"):
            stem = stem[2:]
        for suffix in ("_posts", "_comments"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        return stem or "unknown"
