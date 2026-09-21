"""L1 PDF adapter — ADEA Report 4 (Curriculum) ingestion.

Report 4 is fundamentally different from SDE1/2/3 (which are tabular numeric
metrics). SDE4 is a 200-page narrative survey of curriculum coverage:
section descriptions, assessment methods, table-of-contents pages, free-text
responses. The natural V1 shape is **one L1Document node per page** with
source_tier=L1, rank=preferred, and the page text searchable via the
hybrid index per ADR-002.

V2 can extract per-school + per-curriculum-topic structured records once a
schema exists for curriculum offerings; that work is GAP-045 cont'd.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.shared.content_hash import content_hash_str
from src.shared.timestamps import utc_now

_CYCLE_RE = re.compile(r"(20\d{2})[\-_](\d{2})")
_CYCLE_RE_FULL = re.compile(r"(20\d{2})20(\d{2})")     # "20232024" → 2023-24


@dataclass(frozen=True)
class L1PDFPage:
    """One page of an ADEA PDF survey, normalized for graph ingestion."""

    document_id: str
    source_name: str
    page_number: int
    cycle_year: str | None
    title: str
    body: str
    raw_path: str
    ingested_utc: datetime


@dataclass(frozen=True)
class L1PDFResult:
    cycle_year: str | None
    pages: list[L1PDFPage]
    raw_path: str


class L1PDFAdapter:
    """Pure-Python PDF adapter for ADEA Report 4 (Curriculum) and similar.

    `parse()` opens the PDF via `pdfplumber` and extracts per-page text;
    `from_pages()` is the test seam — pass an explicit list of (page_no, text)
    pairs to bypass the PDF parser.
    """

    source_tier = "L1"

    def parse(
        self,
        payload_path: Path,
        *,
        source_name: str = "ADEA SDE4",
    ) -> L1PDFResult:
        try:
            import pdfplumber  # noqa: PLC0415 — optional dep, lazy
        except ImportError as e:  # pragma: no cover
            raise ImportError(
                "L1PDFAdapter requires `pdfplumber`. "
                "Install with `pip install pdfplumber`.",
            ) from e

        pages: list[tuple[int, str]] = []
        with pdfplumber.open(payload_path) as pdf:
            for idx, page in enumerate(pdf.pages, start=1):
                text = (page.extract_text() or "").strip()
                if text:
                    pages.append((idx, text))
        return self.from_pages(pages, payload_path, source_name=source_name)

    def from_pages(
        self,
        pages: list[tuple[int, str]],
        payload_path: Path,
        *,
        source_name: str = "ADEA SDE4",
    ) -> L1PDFResult:
        cycle = self._cycle_from_filename(Path(payload_path).name)
        now = utc_now()
        out_pages: list[L1PDFPage] = []
        for page_no, text in pages:
            title = self._first_line_title(text)
            doc_id = f"l1_doc:{content_hash_str(str(payload_path) + ':' + str(page_no))[:16]}"
            out_pages.append(L1PDFPage(
                document_id=doc_id, source_name=source_name,
                page_number=page_no, cycle_year=cycle,
                title=title, body=text,
                raw_path=str(payload_path), ingested_utc=now,
            ))
        return L1PDFResult(cycle_year=cycle, pages=out_pages, raw_path=str(payload_path))

    @staticmethod
    def _first_line_title(text: str) -> str:
        for line in text.splitlines():
            cleaned = line.strip()
            if cleaned:
                return cleaned[:200]
        return ""

    @staticmethod
    def _cycle_from_filename(name: str) -> str | None:
        m = _CYCLE_RE.search(name) or _CYCLE_RE_FULL.search(name)
        if not m:
            return None
        return f"{m.group(1)}-{m.group(2)}"
