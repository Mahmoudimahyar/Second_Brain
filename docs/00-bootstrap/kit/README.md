# Bootstrap kit (archived)

SecBrain was started from a generic "AI-agent-optimized repository" bootstrap kit: a docs
scaffold, role harnesses, a skill dispatcher, and a rule that the agent interviews, researches,
and fills the docs **before** writing feature code.

These two files are the kit's original entry points, kept for provenance:

| File | What it was |
|---|---|
| [`START_HERE.md`](START_HERE.md) | The kit's original instructions — "design the whole thing up front, then build one validated vertical slice at a time." |
| [`START_HERE_FINAL.md`](START_HERE_FINAL.md) | The merged kit index (role harnesses, project modes, mandatory skills, continuous research, GraphRAG/MCP requirement). |

They describe how the repository was *bootstrapped*, not how SecBrain works. Some paths they
mention (add-on READMEs, a setup guide, a patches archive) were kit scaffolding that has since
been folded into [`AGENTS.md`](../../../AGENTS.md) and removed; they remain in git history.

What survived from the kit and is still load-bearing:

- [`AGENTS.md`](../../../AGENTS.md) — the operating rules for coding agents, since extended with
  the project's own anti-drift gates.
- [`PROMPTS/SKILLS/`](../../../PROMPTS/SKILLS/) and
  [`PROMPTS/ROLE_HARNESSES/`](../../../PROMPTS/ROLE_HARNESSES/) — the skill and role library
  `AGENTS.md` dispatches to.
- The numbered `docs/` layout.

For the project itself, start at the [repository README](../../../README.md) or the
[documentation index](../../README.md).
