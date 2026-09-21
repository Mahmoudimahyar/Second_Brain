# CLAUDE.md

Follow `AGENTS.md`.

## Claude Code-specific behavior

- Use planning for complex tasks.
- Prefer small, reviewable diffs. **Never squash a whole release into one commit** (a 700-file diff hides wiring gaps — see `docs/00-bootstrap/why-drift-happened.md`).
- Use MCP/GraphRAG tools before broad file reads.
- For UI changes, use browser automation and check console/network errors.
- After implementation, review your own diff as a skeptical senior engineer.
- Do not start coding until the relevant feature packet is complete.
- If blocked, update `/docs/00-bootstrap/unresolved-questions.md` rather than guessing.

## Wiring Gate (read before claiming anything "done")

- "Tests pass" ≠ "done". A capability is done only when **wired into the real entrypoint**
  (`src/cli.py` / `flows/*.py` / `src/web/routes/*`) — cite the `file:line`. See AGENTS.md §Wiring Gate.
- `docs/00-bootstrap/implementation-status.md` is the **single source of truth** for what
  actually runs. Update it first, then the ADRs/tech-stack. If they disagree, the status file wins.
- "Locked"/ADR-`accepted` = **Decided**, not built. Don't read it as implemented.
- Do not open a new feature area while the V1 core slice is below `Validated` on real data.
