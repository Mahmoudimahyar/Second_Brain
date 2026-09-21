from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import orjson

from src.shared.timestamps import from_iso, from_unix_epoch

DELETED_AUTHORS: frozenset[str] = frozenset({"[deleted]", "[removed]", ""})


@dataclass(frozen=True)
class SDNPost:
    post_id: str
    raw_post_id: str
    thread_id: str
    thread_url: str
    thread_title: str
    category: str
    page_number: int | None
    author_user_id: str | None
    raw_author: str | None
    body: str
    created_utc: datetime
    is_thread_root: bool


@dataclass(frozen=True)
class SDNUser:
    user_id: str
    username: str
    first_seen_utc: datetime


@dataclass(frozen=True)
class SDNThread:
    thread_id: str
    raw_thread_id: str
    title: str
    category: str
    url: str
    reply_count: int | None
    view_count: int | None
    root_post_id: str | None


@dataclass(frozen=True)
class L5SDNResult:
    posts: list[SDNPost]
    users: list[SDNUser]
    threads: list[SDNThread]


class L5SDNAdapter:
    """Adapter for Student Doctor Network thread dumps. Implements FR-1.4 + FR-1.5.

    Layout: a single `sdn_thread_metadata.jsonl` lists threads (with `category`,
    `title`, `thread_id`), and per-thread `thread_<id>_posts.jsonl` files hold
    the chronological posts. The adapter filters by category (default
    "Pre-Dental") and optionally limits to the first N threads for V1.

    Canonical IDs follow `data.md`:
      sdn_post:<thread_id>:<raw_post_id>
      sdn_thread:<thread_id>
      sdn:<author>
    """

    source_tier = "L5"

    def parse(
        self,
        metadata_path: Path,
        posts_dir: Path,
        *,
        category: str | None = "Pre-Dental",
        max_threads: int | None = None,
    ) -> L5SDNResult:
        metadata_path = Path(metadata_path)
        posts_dir = Path(posts_dir)
        if not metadata_path.is_file():
            raise FileNotFoundError(f"SDN metadata file not found: {metadata_path}")
        if not posts_dir.is_dir():
            raise FileNotFoundError(f"SDN posts dir not found: {posts_dir}")

        thread_records: list[dict[str, Any]] = []
        for raw in self._iter_jsonl(metadata_path):
            if category is not None and raw.get("category") != category:
                continue
            if not raw.get("thread_id"):
                continue
            thread_records.append(raw)
            if max_threads is not None and len(thread_records) >= max_threads:
                break

        posts: list[SDNPost] = []
        threads: list[SDNThread] = []
        user_first_seen: dict[str, tuple[str, datetime]] = {}

        for tmeta in thread_records:
            tid = str(tmeta["thread_id"])
            thread_posts_file = posts_dir / f"thread_{tid}_posts.jsonl"
            if not thread_posts_file.is_file():
                threads.append(self._make_thread(tmeta, root_post_id=None))
                continue
            thread_posts = list(self._iter_thread_posts(thread_posts_file, tmeta))
            if not thread_posts:
                threads.append(self._make_thread(tmeta, root_post_id=None))
                continue
            thread_posts.sort(key=lambda p: p.created_utc)
            root_id = thread_posts[0].post_id
            for i, p in enumerate(thread_posts):
                if i == 0:
                    post_with_root = self._mark_root(p, is_root=True)
                else:
                    post_with_root = self._mark_root(p, is_root=False)
                posts.append(post_with_root)
                self._record_user_first_seen(
                    user_first_seen,
                    user_id=post_with_root.author_user_id,
                    username=post_with_root.raw_author,
                    ts=post_with_root.created_utc,
                )
            threads.append(self._make_thread(tmeta, root_post_id=root_id))

        users = [
            SDNUser(user_id=uid, username=uname, first_seen_utc=ts)
            for uid, (uname, ts) in sorted(user_first_seen.items())
        ]
        return L5SDNResult(posts=posts, users=users, threads=threads)

    @classmethod
    def _iter_thread_posts(
        cls, path: Path, thread_meta: dict[str, Any],
    ) -> Iterator[SDNPost]:
        category = str(thread_meta.get("category") or "")
        thread_title = str(thread_meta.get("title") or "")
        thread_url = str(thread_meta.get("thread_url") or "")
        raw_thread_id = str(thread_meta.get("thread_id") or "")
        for raw in cls._iter_jsonl(path):
            post = cls._normalize_post(
                raw,
                category=category,
                thread_title=thread_title,
                thread_url=thread_url,
                raw_thread_id=raw_thread_id,
            )
            if post is not None:
                yield post

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
    def _normalize_post(
        cls,
        raw: dict[str, Any],
        *,
        category: str,
        thread_title: str,
        thread_url: str,
        raw_thread_id: str,
    ) -> SDNPost | None:
        raw_post_id = cls._str_or_none(raw.get("post_id"))
        if not raw_post_id:
            return None
        created = cls._created_utc(raw)
        if created is None:
            return None
        raw_author = cls._author_or_none(raw.get("author"))
        author_user_id = f"sdn:{raw_author}" if raw_author is not None else None
        return SDNPost(
            post_id=f"sdn_post:{raw_thread_id}:{raw_post_id}",
            raw_post_id=raw_post_id,
            thread_id=f"sdn_thread:{raw_thread_id}",
            thread_url=thread_url,
            thread_title=thread_title,
            category=category,
            page_number=cls._int_or_none(raw.get("page_number")),
            author_user_id=author_user_id,
            raw_author=raw_author,
            body=str(raw.get("content_text") or ""),
            created_utc=created,
            is_thread_root=False,  # set by parse() after sorting
        )

    @staticmethod
    def _mark_root(post: SDNPost, *, is_root: bool) -> SDNPost:
        return SDNPost(
            post_id=post.post_id,
            raw_post_id=post.raw_post_id,
            thread_id=post.thread_id,
            thread_url=post.thread_url,
            thread_title=post.thread_title,
            category=post.category,
            page_number=post.page_number,
            author_user_id=post.author_user_id,
            raw_author=post.raw_author,
            body=post.body,
            created_utc=post.created_utc,
            is_thread_root=is_root,
        )

    @staticmethod
    def _make_thread(meta: dict[str, Any], *, root_post_id: str | None) -> SDNThread:
        raw_thread_id = str(meta["thread_id"])
        return SDNThread(
            thread_id=f"sdn_thread:{raw_thread_id}",
            raw_thread_id=raw_thread_id,
            title=str(meta.get("title") or ""),
            category=str(meta.get("category") or ""),
            url=str(meta.get("thread_url") or ""),
            reply_count=L5SDNAdapter._int_or_none(meta.get("reply_count")),
            view_count=L5SDNAdapter._int_or_none(meta.get("view_count")),
            root_post_id=root_post_id,
        )

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
        iso = raw.get("timestamp_iso")
        if iso:
            try:
                return from_iso(str(iso))
            except (ValueError, TypeError):
                pass
        epoch = raw.get("created_utc")
        if epoch is not None:
            try:
                return from_unix_epoch(epoch)
            except (ValueError, OverflowError, TypeError):
                return None
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
