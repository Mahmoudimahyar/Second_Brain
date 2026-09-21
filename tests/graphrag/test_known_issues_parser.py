"""Tests for `tools/graphrag/parsers/known_issues.py`."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.graphrag.parsers import known_issues
from tools.graphrag.parsers.base import accepts_path
from tools.graphrag.types import NodeType

pytestmark = pytest.mark.unit


class _StubParser:
    ACCEPTS = known_issues.ACCEPTS

    def parse(self, file_path, repo_root):  # pragma: no cover
        return None


def test_accepts_known_issues_md() -> None:
    p = _StubParser()
    assert accepts_path(p, "docs/05-features/01-slice/known-issues.md")
    assert accepts_path(p, "docs/maintenance/known-issues.md")


def test_rejects_unrelated_md() -> None:
    p = _StubParser()
    assert not accepts_path(p, "docs/05-features/01-slice/README.md")
    assert not accepts_path(p, "docs/01-core/product-vision.md")


def _write_ki(tmp_repo: Path, repo_relative: str, body: str) -> Path:
    path = tmp_repo / repo_relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_extracts_table_rows(tmp_repo: Path) -> None:
    body = (
        "# Known Issues\n\n"
        "| ID | Issue | Category | Severity | Workaround | Resolution plan |\n"
        "|---|---|---|---|---|---|\n"
        "| KI-001 | Cache TTL changed | Cost | High | Pin ttl=3600 | Lint rule |\n"
        "| KI-002 | HNSW degrades under deletes | Performance | Med | Rebuild nightly | Cron job |\n"
    )
    path = _write_ki(tmp_repo, "docs/05-features/01-slice/known-issues.md", body)
    result = known_issues.parse(path, tmp_repo)

    issues = [n for n in result.nodes if n.node_type == NodeType.KNOWN_ISSUE]
    ids = sorted(n.properties["ki_id"] for n in issues)
    assert ids == ["KI-001", "KI-002"]
    ki1 = next(n for n in issues if n.properties["ki_id"] == "KI-001")
    assert ki1.properties["feature_slug"] == "01-slice"
    assert ki1.properties["severity"] == "high"
    assert ki1.properties["category"] == "Cost"
    assert "Cache TTL" in ki1.properties["description"]
    assert ki1.properties["workaround"] == "Pin ttl=3600"
    assert ki1.properties["resolution_plan"] == "Lint rule"


def test_skips_empty_placeholder_rows(tmp_repo: Path) -> None:
    body = (
        "| ID | Issue | Category | Severity |\n"
        "|---|---|---|---|\n"
        "| KI-001 | (empty placeholder) | x | low |\n"
        "| KI-002 | Real issue | Cost | Med |\n"
    )
    path = _write_ki(tmp_repo, "docs/05-features/01-slice/known-issues.md", body)
    result = known_issues.parse(path, tmp_repo)

    ids = sorted(n.properties["ki_id"] for n in result.nodes if n.node_type == NodeType.KNOWN_ISSUE)
    assert ids == ["KI-002"]


def test_skips_rows_without_ki_id(tmp_repo: Path) -> None:
    body = (
        "| ID | Issue | Category | Severity |\n"
        "|---|---|---|---|\n"
        "| TBD | TBD | TBD | TBD |\n"
        "| KI-005 | Real | Data | Low |\n"
    )
    path = _write_ki(tmp_repo, "docs/05-features/01-slice/known-issues.md", body)
    result = known_issues.parse(path, tmp_repo)

    assert [n.properties["ki_id"] for n in result.nodes] == ["KI-005"]


def test_no_feature_slug_when_outside_feature_dir(tmp_repo: Path) -> None:
    body = (
        "| ID | Issue | Category | Severity |\n"
        "|---|---|---|---|\n"
        "| KI-001 | Repo-wide thing | Tooling | Med |\n"
    )
    path = _write_ki(tmp_repo, "docs/maintenance/known-issues.md", body)
    result = known_issues.parse(path, tmp_repo)

    issue = next(n for n in result.nodes if n.node_type == NodeType.KNOWN_ISSUE)
    assert issue.properties["feature_slug"] is None
    assert issue.id == "ki:repo:KI-001"


def test_severity_normalized(tmp_repo: Path) -> None:
    body = (
        "| ID | Issue | Category | Severity |\n"
        "|---|---|---|---|\n"
        "| KI-001 | A | x | Medium |\n"
        "| KI-002 | B | x | HIGH |\n"
        "| KI-003 | C | x | critical |\n"
        "| KI-004 | D | x | weird |\n"
    )
    path = _write_ki(tmp_repo, "docs/05-features/01-slice/known-issues.md", body)
    result = known_issues.parse(path, tmp_repo)

    severities = {n.properties["ki_id"]: n.properties["severity"] for n in result.nodes}
    assert severities == {
        "KI-001": "med",
        "KI-002": "high",
        "KI-003": "critical",
        "KI-004": "med",
    }


def test_idempotent(tmp_repo: Path) -> None:
    body = (
        "| ID | Issue | Category | Severity |\n"
        "|---|---|---|---|\n"
        "| KI-001 | A | x | Med |\n"
    )
    path = _write_ki(tmp_repo, "docs/05-features/01-slice/known-issues.md", body)
    a = known_issues.parse(path, tmp_repo)
    b = known_issues.parse(path, tmp_repo)
    assert [n.id for n in a.nodes] == [n.id for n in b.nodes]
