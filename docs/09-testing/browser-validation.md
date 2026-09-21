# Browser Validation

> ⚠️ **Historical (written before V1.5b).** The statement below is no longer true: the repo ships a Next.js operations console in `web/`, with Playwright + axe-core specs under `web/e2e/` and Vitest unit tests. See `web/README.md` for how to run them.

> **V1 has no browser UI.** HITL is CLI + flat YAML files; retrieval is MCP stdio + Python API. This file is preserved as a placeholder for V2 when a web HITL UI lands.

## V1 status

- **Not applicable.** V1 ships:
  - HITL CLI (`hitl pull`, `hitl commit`) — covered by integration tests in `tests/hitl/`.
  - MCP retrieval (stdio) — covered by contract tests in `tests/retrieval/`.
  - HITL reviewer interaction with YAML files — covered by `test_hitl_cli.py::test_pull_commit_round_trip`.
- Any browser-related task that appears in a V1 PR should be redirected to CLI / MCP / Python API testing.

## V2 reopen (preview only)

When a web HITL UI lands in V2:

The agent must:
1. Start the app (`make dev` or equivalent).
2. Open the relevant page.
3. Execute the flow from the feature packet's `ui-flow.md`.
4. Test happy path.
5. Test at least one error path.
6. Check browser console errors (none allowed).
7. Check failed network requests (none allowed unless explicitly part of the error-path test).
8. Check loading states.
9. Check empty states if applicable.
10. Check mobile viewport if relevant.
11. Fix issues and rerun.

A V2 UI task is not complete if the browser flow fails.

Suggested V2 stack (when chosen):
- E2E framework: **Playwright** (Python or TS-binding TBD).
- Component-level tests: TBD at V2 framework pick.

## How V1 substitutes for browser validation

| What browser validation usually checks | V1 substitute |
|---|---|
| User completes a flow without crash | `test_hitl_cli.py` integration tests cover the CLI flow end-to-end. |
| No console errors | structlog log capture in `tests/observability/` — asserts no `error`-level records during happy paths. |
| No failed network requests | `respx` HTTP mocking + cost-regression tests verify expected vendor calls only. |
| Loading / empty / mobile states | CLI has no loading/empty/mobile equivalents in V1. |
| Accessibility | N/A for CLI. V2 web UI must include `axe-core` or equivalent. |

## When this file becomes binding

When a feature packet under `docs/05-features/` adds a `ui-flow.md` AND a `state-machine.md` with web-UI components. At that point, this file becomes the V2 reopen plan, drafted in detail.
