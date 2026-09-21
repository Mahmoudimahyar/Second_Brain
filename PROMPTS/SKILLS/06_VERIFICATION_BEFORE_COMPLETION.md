# Skill: Verification Before Completion

## Trigger
Use before saying a task is complete, fixed, done, passing, implemented, or ready.

## Required evidence
- commands run
- test results
- typecheck/lint results
- browser validation if UI changed
- console/network check if UI changed
- docs updated
- files changed
- known remaining issues

## Wiring + doc↔code reconciliation (added 2026-05-29 — mandatory)

Unit tests passing is **necessary but not sufficient**. A module can be fully tested and
still be unreachable from the product (this caused the 2026-05 drift — see
`docs/00-bootstrap/why-drift-happened.md`). Before claiming done, also produce:

- **Wiring site** — the `file:line` in a real entrypoint (`src/cli.py`, `flows/*.py`,
  `src/web/routes/*`) that invokes the capability on the real path. If none exists, the
  status is `Built`, **not done**. Log a gap.
- **Stub-wiring scan** — grep for collaborators constructed with `None`/no-op (e.g.
  `ConflictResolver()` with no judge) and for types referenced but never constructed
  (e.g. `HybridIndex`). Any hit = not done.
- **ADR "Related code" existence check** — every file an ADR lists under "Related code"
  must exist. Run: `for f in <files>; do test -f "$f" || echo MISSING $f; done`.
- **Status reconciliation** — update the capability's row in
  `docs/00-bootstrap/implementation-status.md` (`Built`/`Wired`/`Validated`) with the
  wiring site. Confirm no doc (non-negotiables, "Locked" table, ADR) claims "done" for
  anything below `Wired`.
- **Real-data check** — state whether it ran on `External Data/`. If not, status is at
  most `Wired`, never `Validated`.

## Hard rule
Do not claim success without evidence from actual commands or clearly state what was not run.
**And do not claim "done" without a cited non-test wiring site.** "Tests pass" ≠ "wired".
