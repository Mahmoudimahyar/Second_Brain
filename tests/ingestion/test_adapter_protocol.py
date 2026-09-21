"""Tests for `src.ingestion.adapters.base.SourceAdapter` Protocol conformance."""

from __future__ import annotations

from src.ingestion.adapters.base import SourceAdapter
from src.ingestion.adapters.l1_excel import L1ExcelAdapter
from src.ingestion.adapters.l5_reddit import L5RedditAdapter
from src.ingestion.adapters.l5_sdn import L5SDNAdapter


def test_l1_excel_adapter_has_source_tier() -> None:
    assert L1ExcelAdapter.source_tier == "L1"


def test_l5_reddit_adapter_has_source_tier() -> None:
    assert L5RedditAdapter.source_tier == "L5"


def test_l5_sdn_adapter_has_source_tier() -> None:
    assert L5SDNAdapter.source_tier == "L5"


def test_protocol_definition_is_importable() -> None:
    # Importing the Protocol exercises its module's top-level statements.
    assert SourceAdapter is not None
