"""L2 unstructured-truth HTML adapter per Phase 2 + ADR-005 trust ladder.

L2 covers official-source articles that aren't structured tables (ADEA blog,
ADA news, ASDA blog, school admissions pages). Each HTML file becomes one
`L2Document` canonical record:

  document_id: l2_doc:<sha256-16>
  source_name: per-file or per-dump (caller supplies)
  url: extracted from <link rel="canonical">, <meta og:url>, or filename hint
  title: <title> or first <h1>
  body: text after tag-stripping, whitespace-normalized
  published_utc: from <meta name="article:published_time"> / <time datetime>

Pure-Python tag stripping (no bs4 dep); good enough for V1 official-source
HTML which is typically clean blog markup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.shared.content_hash import content_hash_str
from src.shared.timestamps import from_iso, utc_now

# Pre-compiled tag/whitespace regexes. Order matters: script/style first,
# then tags, then entities.
_SCRIPT_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_CANON_URL_RE = re.compile(
    r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_META_URL_RE = re.compile(
    r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_META_PUBLISHED_RE = re.compile(
    r'<meta[^>]+(?:name|property)=["\']'
    r'(?:article:published_time|date|publish_date|pubdate)'
    r'["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_TIME_DATETIME_RE = re.compile(
    r'<time[^>]+datetime=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_HTML_ENTITIES: dict[str, str] = {
    "&amp;": "&", "&lt;": "<", "&gt;": ">",
    "&quot;": '"', "&apos;": "'", "&#39;": "'", "&nbsp;": " ",
}


@dataclass(frozen=True)
class L2Document:
    document_id: str
    source_name: str
    url: str | None
    title: str
    body: str
    published_utc: datetime | None
    raw_path: str           # original file path
    ingested_utc: datetime


@dataclass(frozen=True)
class L2IngestResult:
    documents: list[L2Document]


class L2HtmlAdapter:
    """Pure-Python HTML adapter for official L2 sources.

    No bs4 dependency; uses regex tag-stripping that handles common cases
    (clean blog markup, simple semantic HTML). Pathological HTML (broken tags,
    JS-rendered content) is the caller's problem — they should pre-render via
    headless browser before feeding here.
    """

    source_tier = "L2"

    def parse(
        self,
        payload_paths: list[Path],
        *,
        source_name: str = "L2 source",
    ) -> L2IngestResult:
        documents: list[L2Document] = []
        now = utc_now()
        for path in payload_paths:
            p = Path(path)
            if not p.is_file():
                continue
            html = p.read_text(encoding="utf-8", errors="replace")
            documents.append(self._normalize(html, source_name=source_name,
                                              raw_path=str(p), now=now))
        return L2IngestResult(documents=documents)

    def parse_string(
        self,
        html: str,
        *,
        source_name: str = "L2 source",
        raw_path: str = "<inline>",
    ) -> L2Document:
        return self._normalize(
            html, source_name=source_name, raw_path=raw_path, now=utc_now(),
        )

    @classmethod
    def _normalize(
        cls, html: str, *, source_name: str, raw_path: str, now: datetime,
    ) -> L2Document:
        title = cls._extract_title(html)
        body = cls._extract_body(html)
        url = cls._extract_url(html)
        published = cls._extract_published(html)
        doc_id = f"l2_doc:{content_hash_str(raw_path + '|' + body)[:16]}"
        return L2Document(
            document_id=doc_id,
            source_name=source_name,
            url=url,
            title=title,
            body=body,
            published_utc=published,
            raw_path=raw_path,
            ingested_utc=now,
        )

    @classmethod
    def _extract_title(cls, html: str) -> str:
        m = _TITLE_RE.search(html)
        if m:
            return cls._clean(m.group(1))
        m = _H1_RE.search(html)
        if m:
            return cls._clean(m.group(1))
        return ""

    @classmethod
    def _extract_body(cls, html: str) -> str:
        # Drop scripts/styles, then strip all remaining tags.
        stripped = _SCRIPT_RE.sub(" ", html)
        text = _TAG_RE.sub(" ", stripped)
        return cls._clean(text)

    @classmethod
    def _extract_url(cls, html: str) -> str | None:
        m = _CANON_URL_RE.search(html) or _META_URL_RE.search(html)
        return m.group(1) if m else None

    @classmethod
    def _extract_published(cls, html: str) -> datetime | None:
        m = _META_PUBLISHED_RE.search(html) or _TIME_DATETIME_RE.search(html)
        if not m:
            return None
        try:
            return from_iso(m.group(1))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _clean(text: str) -> str:
        # Decode common HTML entities; collapse whitespace.
        for entity, char in _HTML_ENTITIES.items():
            text = text.replace(entity, char)
        return _WS_RE.sub(" ", text).strip()
