"""Conftest for ``tests/conflict/`` — autouse the offline-mode env var.

The V1.5c BAML heuristics (``heuristic_make_question`` /
``heuristic_paraphrase`` / ``heuristic_verify_claim``) raise ``RuntimeError``
unless ``SECBRAIN_OFFLINE=1`` is set, per the W1-1 gap-audit remediation.
The offline guard exists to prevent the prior session's failure mode of
shipping the heuristics as the production code path.

Most tests in ``tests/conflict/`` legitimately use heuristics to avoid
LLM round-trips at unit-test speed. This fixture opts those tests into
the offline mode without polluting other test packages' env.

Tests that exercise the *production* path (``test_baml_gateway_routing.py``)
override the env var per-test via ``monkeypatch.delenv(...)`` /
``monkeypatch.setenv(...)``.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _enable_secbrain_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set ``SECBRAIN_OFFLINE=1`` for every conflict test by default."""

    monkeypatch.setenv("SECBRAIN_OFFLINE", "1")
