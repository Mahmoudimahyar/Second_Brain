## What and why

<!-- One slice / one work package per PR. Link the feature packet, ADR, or GAP id. -->

## Wiring site

<!-- "Tests pass" is not "done". Name the non-test call site that invokes this on the real path. -->

- Entrypoint (`src/cli.py` / `flows/*.py` / `src/web/routes/*` / MCP tool): `path:line`
- Status moved in `docs/00-bootstrap/implementation-status.md`: `Decided → Built → Wired → Validated`

## Evidence

<!-- Commands you ran and what they printed. Eval deltas if retrieval/extraction quality could move. -->

```
pytest -q ...
```

## Definition of done

- [ ] Acceptance criteria met
- [ ] Tests written first; unit + integration green (integration exercises the **real wiring**, not a mock-only path)
- [ ] `ruff check` + `mypy` clean (and `pnpm typecheck` / `pnpm test` if `web/` changed)
- [ ] **No stub wiring** — no `None` / no-op collaborators, no referenced-but-unconstructed types
- [ ] Ran on real data, or stated why not (`Validated` vs `Wired`)
- [ ] `implementation-status.md` row updated; docs reconciled (nothing claims "done" below `Wired`)
- [ ] UI changes checked in a browser (console + network clean)
- [ ] No secrets, no real usernames / identifiable forum text, no licensed data in the diff
- [ ] Diff is small enough to actually review
