# AI-Agent-Optimized Repository Bootstrap Kit

Use this kit to create a new codebase that is optimized for:
- accurate coding-agent behavior
- low token usage
- structured documentation
- GraphRAG/MCP retrieval
- test-driven development
- browser-validated UI flows
- clean, modular, maintainable code

## How to use this kit

1. Copy all files into the root of a new repository.
2. Open the repo in Claude Code, Codex, Cursor, or another coding agent.
3. Give the agent `PROMPTS/MASTER_BOOTSTRAP_PROMPT.md`.
4. Do not let the agent code immediately.
5. The agent must first interview you or ingest your uploaded documents.
6. The agent fills the `/docs` structure.
7. The agent identifies required environment variables and writes `.env.example`.
8. You fill the real `.env`.
9. The agent creates the first vertical implementation slice.
10. The agent writes tests first, implements, validates, updates docs, and produces a validation report.

## Critical rule

Do not ask the agent to build the entire product in one giant pass.

Instead:
- make the agent design the whole product and repo structure upfront
- then build one vertical slice at a time
- each slice must pass tests and browser validation before the next slice

A giant “build everything nonstop” pass creates an unreviewable mess. The correct version is nonstop execution per validated slice.
