"""WP1 doc-lint — the gate test.

Runs the doc-lint against the *real* repo. This is what wires the guardrail
into the test suite: any future drift (an accepted ADR naming a missing file, a
stale "Locked" claim for a below-Wired capability, an un-allowlisted bare
ConflictResolver) fails `pytest` here.
"""

from __future__ import annotations

import pytest

from tools.doc_lint.check_status_truth import (
    check_adr_related_code,
    check_status_truth_claims,
    check_stub_wiring,
    find_repo_root,
    main,
)

REPO_ROOT = find_repo_root()


@pytest.mark.integration
def test_check_a_adr_related_code_clean() -> None:
    violations = check_adr_related_code(REPO_ROOT)
    assert violations == [], "\n".join(f"{v.location}: {v.message}" for v in violations)


@pytest.mark.integration
def test_check_b_status_truth_clean() -> None:
    violations = check_status_truth_claims(REPO_ROOT)
    assert violations == [], "\n".join(f"{v.location}: {v.message}" for v in violations)


@pytest.mark.integration
def test_check_c_stub_wiring_clean() -> None:
    violations = check_stub_wiring(REPO_ROOT)
    assert violations == [], "\n".join(f"{v.location}: {v.message}" for v in violations)


@pytest.mark.integration
def test_doc_lint_main_exits_zero() -> None:
    assert main([]) == 0
