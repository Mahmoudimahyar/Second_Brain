"""Tests for `src.ingestion.adapters.l1_pdf.L1PDFAdapter`.

Uses the `from_pages` test seam so we don't have to build real PDFs in unit
tests. Real PDF parsing is exercised only by the live SDE4 ingest smoke.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from src.ingestion.adapters.l1_pdf import L1PDFAdapter, L1PDFResult


def test_from_pages_extracts_title_and_cycle(tmp_path: Path) -> None:
    adapter = L1PDFAdapter()
    payload = tmp_path / "SDE4_2023-24.pdf"
    pages = [
        (1, "2023-24 Survey of Dental Education\nReport 4 - Curriculum\nTable of Contents"),
        (2, "SECTION 1: COMPETENCY\nMethods of Instruction..."),
    ]

    result = adapter.from_pages(pages, payload, source_name="ADEA SDE4 2023-24")

    assert isinstance(result, L1PDFResult)
    assert result.cycle_year == "2023-24"
    assert len(result.pages) == 2
    assert result.pages[0].title.startswith("2023-24 Survey")
    assert result.pages[1].title == "SECTION 1: COMPETENCY"
    assert all(p.source_name == "ADEA SDE4 2023-24" for p in result.pages)


def test_from_pages_assigns_deterministic_document_ids(tmp_path: Path) -> None:
    """Same (path, page_no) → same document_id (idempotent re-ingest)."""

    payload = tmp_path / "SDE4_2023-24.pdf"
    pages = [(1, "page one text")]
    a = L1PDFAdapter().from_pages(pages, payload).pages[0].document_id
    b = L1PDFAdapter().from_pages(pages, payload).pages[0].document_id
    assert a == b
    assert a.startswith("l1_doc:")


def test_from_pages_filters_empty_pages_by_caller(tmp_path: Path) -> None:
    """The adapter trusts its input — empty-text pages are caller-filtered."""

    payload = tmp_path / "SDE4_2024-25.pdf"
    pages = [(1, "real page"), (2, "another real page")]
    result = L1PDFAdapter().from_pages(pages, payload)
    assert len(result.pages) == 2


def test_cycle_from_filename_handles_old_naming(tmp_path: Path) -> None:
    """Older ADEA PDFs use 'Report 4 20232024.pdf' (no separator)."""

    payload = tmp_path / "Dental Education Series  Report 4 20232024.pdf"
    result = L1PDFAdapter().from_pages([(1, "header")], payload)
    # The 8-digit pair "20232024" parses as 2023-24 by the regex.
    assert result.cycle_year == "2023-24"


def test_cycle_from_filename_returns_none_when_unparseable(tmp_path: Path) -> None:
    payload = tmp_path / "unparseable.pdf"
    result = L1PDFAdapter().from_pages([(1, "header")], payload)
    assert result.cycle_year is None


def test_l1pdf_page_is_frozen(tmp_path: Path) -> None:
    page = L1PDFAdapter().from_pages(
        [(1, "x")], tmp_path / "SDE4_2024-25.pdf",
    ).pages[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        page.title = "other"  # type: ignore[misc]


def test_source_tier_constant() -> None:
    assert L1PDFAdapter.source_tier == "L1"


def test_title_truncated_to_max_length(tmp_path: Path) -> None:
    long_first_line = "x" * 500
    result = L1PDFAdapter().from_pages(
        [(1, long_first_line)], tmp_path / "SDE4_2024-25.pdf",
    )
    assert len(result.pages[0].title) <= 200


def test_title_skips_blank_leading_lines(tmp_path: Path) -> None:
    pages = [(1, "\n\n   \nReal Title Line\nBody text")]
    result = L1PDFAdapter().from_pages(pages, tmp_path / "SDE4_2024-25.pdf")
    assert result.pages[0].title == "Real Title Line"
