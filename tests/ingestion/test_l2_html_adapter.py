"""Tests for `src.ingestion.adapters.l2_html.L2HtmlAdapter`."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.ingestion.adapters.l2_html import L2Document, L2HtmlAdapter, L2IngestResult

_SAMPLE_BLOG_HTML = """\
<!DOCTYPE html>
<html>
<head>
  <title>ADEA Releases 2024-25 Dental School Tuition Report</title>
  <link rel="canonical" href="https://adea.org/news/2024-25-tuition-report" />
  <meta property="og:url" content="https://adea.org/news/2024-25-tuition-report" />
  <meta name="article:published_time" content="2024-09-15T14:30:00+00:00" />
  <style>body { font: 14px sans-serif; }</style>
</head>
<body>
  <script>analytics.track('pageview');</script>
  <h1>ADEA Releases 2024-25 Dental School Tuition Report</h1>
  <article>
    <p>The American Dental Education Association today published its
       annual tuition and admissions report covering all 70+ U.S. dental
       schools. Average resident tuition rose 3.2% year-over-year.</p>
    <p>Notable: NYU College of Dentistry remains the highest, at $94,108.</p>
  </article>
</body>
</html>
"""


def test_parse_string_extracts_title_body_url(tmp_path: Path) -> None:
    adapter = L2HtmlAdapter()
    doc = adapter.parse_string(_SAMPLE_BLOG_HTML, source_name="ADEA Blog")

    assert isinstance(doc, L2Document)
    assert "ADEA Releases 2024-25" in doc.title
    assert "94,108" in doc.body
    assert doc.url == "https://adea.org/news/2024-25-tuition-report"
    assert doc.source_name == "ADEA Blog"
    assert doc.document_id.startswith("l2_doc:")
    assert doc.published_utc == datetime(2024, 9, 15, 14, 30, tzinfo=UTC)


def test_strips_script_and_style_blocks() -> None:
    doc = L2HtmlAdapter().parse_string(_SAMPLE_BLOG_HTML)
    assert "analytics" not in doc.body
    assert "pageview" not in doc.body
    assert "font: 14px" not in doc.body


def test_collapses_whitespace() -> None:
    html = "<p>Line 1.\n\n\n   Line 2.\n\t\tLine 3.</p>"
    doc = L2HtmlAdapter().parse_string(html)
    assert doc.body == "Line 1. Line 2. Line 3."


def test_handles_missing_canonical_url() -> None:
    html = "<html><head><title>Test</title></head><body><p>x</p></body></html>"
    doc = L2HtmlAdapter().parse_string(html)
    assert doc.url is None


def test_handles_missing_title_falls_back_to_h1() -> None:
    html = "<html><body><h1>Fallback Title</h1><p>x</p></body></html>"
    doc = L2HtmlAdapter().parse_string(html)
    assert "Fallback Title" in doc.title


def test_handles_time_tag_for_published_date() -> None:
    html = (
        "<html><head><title>x</title></head>"
        '<body><time datetime="2025-06-01T12:00:00+00:00">June 1, 2025</time>'
        "<p>body</p></body></html>"
    )
    doc = L2HtmlAdapter().parse_string(html)
    assert doc.published_utc == datetime(2025, 6, 1, 12, 0, tzinfo=UTC)


def test_html_entities_decoded() -> None:
    html = "<html><head><title>x</title></head><body><p>Tom &amp; Jerry &lt;laughs&gt;</p></body></html>"
    doc = L2HtmlAdapter().parse_string(html)
    assert "Tom & Jerry" in doc.body
    assert "<laughs>" in doc.body


def test_parse_reads_files_from_disk(tmp_path: Path) -> None:
    p1 = tmp_path / "post1.html"
    p2 = tmp_path / "post2.html"
    p1.write_text(_SAMPLE_BLOG_HTML, encoding="utf-8")
    p2.write_text(_SAMPLE_BLOG_HTML.replace("2024-25", "2025-26"), encoding="utf-8")

    result = L2HtmlAdapter().parse([p1, p2], source_name="ADEA Blog")

    assert isinstance(result, L2IngestResult)
    assert len(result.documents) == 2
    assert all(d.source_name == "ADEA Blog" for d in result.documents)


def test_parse_skips_missing_files(tmp_path: Path) -> None:
    p1 = tmp_path / "exists.html"
    p1.write_text(_SAMPLE_BLOG_HTML, encoding="utf-8")
    missing = tmp_path / "nope.html"

    result = L2HtmlAdapter().parse([p1, missing])
    assert len(result.documents) == 1


def test_deterministic_document_id() -> None:
    """Same raw_path + body → same document_id (idempotent re-ingest)."""

    html = "<title>X</title><body>same content</body>"
    a = L2HtmlAdapter().parse_string(html, raw_path="path/a.html")
    b = L2HtmlAdapter().parse_string(html, raw_path="path/a.html")
    assert a.document_id == b.document_id


def test_different_raw_paths_produce_different_ids() -> None:
    """Two HTML files with identical content at different paths get distinct IDs."""

    html = "<title>X</title><body>same content</body>"
    a = L2HtmlAdapter().parse_string(html, raw_path="path/a.html")
    b = L2HtmlAdapter().parse_string(html, raw_path="path/b.html")
    assert a.document_id != b.document_id


def test_source_tier_constant() -> None:
    assert L2HtmlAdapter.source_tier == "L2"


def test_invalid_published_date_yields_none() -> None:
    html = (
        '<meta name="article:published_time" content="not-a-date" />'
        "<title>x</title><body>body</body>"
    )
    doc = L2HtmlAdapter().parse_string(html)
    assert doc.published_utc is None


def test_dataclass_is_frozen() -> None:
    doc = L2Document(
        document_id="x", source_name="s", url=None,
        title="t", body="b", published_utc=None,
        raw_path="p", ingested_utc=datetime.now(UTC),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        doc.title = "y"  # type: ignore[misc]
