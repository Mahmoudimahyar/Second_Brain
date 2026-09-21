"""Doc-lint guardrails (V1.7 WP1).

`check_status_truth` enforces doc↔code truth so the drift documented in
`docs/00-bootstrap/why-drift-happened.md` cannot silently reappear:

- check A — every ``accepted`` ADR's (uncaveated) ``Related code`` files exist;
- check B — no non-negotiable / "Locked" row claims a capability that
  `implementation-status.md` marks below ``Wired`` without a target marker;
- check C — no stub wiring (``ConflictResolver(`` with no judge/web-verifier)
  outside ``tests/`` beyond an explicit, shrinking allowlist.
"""
