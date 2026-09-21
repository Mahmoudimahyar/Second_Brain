"""Prefect 3 flow scaffolds per ADR-010.

These modules are intentionally lightweight wrappers around the same functions
called by `src.cli`. They add scheduling, retries, and observability without
duplicating business logic.

Install:
  pip install "prefect>=3"

Run locally:
  prefect server start                       # background terminal #1
  python -m flows.full_sweep                 # one-shot full sweep
  python -m flows.pass1_structural --once    # ad-hoc single-pass run

Deploy a daily schedule (ADR-010 §"Architecture impact"):
  prefect deployment build flows/full_sweep.py:full_sweep \
      --name nightly --cron "0 4 * * *"
  prefect agent start

These files are excluded from `pytest` / `mypy --strict` to keep Prefect a
genuinely optional install. A `flows.test_smoke` AST parse runs in CI to
confirm syntactic validity without requiring Prefect to be installed.
"""
