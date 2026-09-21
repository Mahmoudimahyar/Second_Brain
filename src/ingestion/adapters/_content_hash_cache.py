"""V1.6a — per-page content-addressable cache for the website-crawl adapter.

Layout per ADR-019: `data/web_cache/<domain>/<sha256-16-of-url>.<ext>`
with sibling `<sha256-16-of-url>.meta.json` carrying URL + headers +
content-hash + bytes.

Cache hit semantics per FR-1.6a-2.9: if `content_hash` unchanged AND
ETag / Last-Modified unchanged AND `mime` unchanged → adapter returns
the cached normalized record without re-running extraction.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


def url_key(url: str) -> str:
    """16-hex-char sha256 prefix; matches the V1 cache-key convention."""

    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def content_hash(body: bytes) -> str:
    """64-hex-char sha256 — matches V1's `content_hash_str` shape."""

    return hashlib.sha256(body).hexdigest()


def fqdn_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


@dataclass(frozen=True)
class CacheMeta:
    """Sidecar `<key>.meta.json` payload."""

    url: str
    etag: str | None
    last_modified: str | None
    content_hash: str
    bytes_: int
    mime: str
    fetched_at: datetime


class ContentHashCache:
    """File-backed per-page cache.

    The body file holds the raw bytes; the meta file is JSON. Both are
    keyed by `url_key(url)`. The body's extension follows the MIME so
    operators can browse the cache by hand (`.html`, `.pdf`, `.jpg`, …).
    """

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def get_meta(self, url: str) -> CacheMeta | None:
        meta_path = self._meta_path(url)
        if not meta_path.exists():
            return None
        try:
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        try:
            return CacheMeta(
                url=str(payload["url"]),
                etag=payload.get("etag"),
                last_modified=payload.get("last_modified"),
                content_hash=str(payload["content_hash"]),
                bytes_=int(payload["bytes_"]),
                mime=str(payload["mime"]),
                fetched_at=datetime.fromisoformat(str(payload["fetched_at"])),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def get_body(self, url: str, *, mime: str) -> bytes | None:
        body_path = self._body_path(url, mime=mime)
        if not body_path.exists():
            return None
        try:
            return body_path.read_bytes()
        except OSError:
            return None

    # ------------------------------------------------------------------
    # Write API
    # ------------------------------------------------------------------

    def put(self, *, body: bytes, meta: CacheMeta) -> None:
        body_path = self._body_path(meta.url, mime=meta.mime)
        body_path.parent.mkdir(parents=True, exist_ok=True)
        body_path.write_bytes(body)
        meta_path = self._meta_path(meta.url)
        meta_path.write_text(
            json.dumps({
                "url": meta.url,
                "etag": meta.etag,
                "last_modified": meta.last_modified,
                "content_hash": meta.content_hash,
                "bytes_": meta.bytes_,
                "mime": meta.mime,
                "fetched_at": meta.fetched_at.isoformat(),
            }),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _body_path(self, url: str, *, mime: str) -> Path:
        return self._domain_dir(url) / f"{url_key(url)}{_ext_for(mime)}"

    def _meta_path(self, url: str) -> Path:
        return self._domain_dir(url) / f"{url_key(url)}.meta.json"

    def _domain_dir(self, url: str) -> Path:
        return self._cache_dir / fqdn_of(url)


_EXT_BY_PREFIX: dict[str, str] = {
    "text/html": ".html",
    "application/xhtml+xml": ".html",
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel": ".xls",
    "text/csv": ".csv",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "text/plain": ".txt",
    "application/json": ".json",
}


def _ext_for(mime: str) -> str:
    base = (mime or "").split(";", 1)[0].strip().lower()
    return _EXT_BY_PREFIX.get(base, ".bin")


__all__ = [
    "CacheMeta",
    "ContentHashCache",
    "content_hash",
    "fqdn_of",
    "url_key",
]
