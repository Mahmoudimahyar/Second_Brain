# `tools/graphrag/` — Repo MCP Context Server

> Indexes the SecBrain repo (docs, code, tests, feature packets) into a graph + vector store so the coding agent has low-token retrieval before broad file reads. This is **gate #6** per CLAUDE.md.
>
> **Distinct from** the V1 product engine MCP under `src/mcp/` — see `docs/04-architecture/system-overview.md` "Two distinct GraphRAG deployments".

## Status

Phase 0 (scaffolding) — **in progress**. Markdown parser landed. Remaining phases per `IMPLEMENTATION_PLAN.md`.

## Design docs (read before contributing)

- [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) — phased build plan
- [`architecture.md`](architecture.md) — component design + diagram
- [`schema.md`](schema.md) — node + edge types with full property definitions
- [`retrieval-policy.md`](retrieval-policy.md) — per-tool retrieval algorithms
- [`verification-checklist.md`](verification-checklist.md) — gate #6 checklist
- [`verification-harness.md`](verification-harness.md) — concrete tests per checklist item
- [`MCP_SERVER_REQUIREMENTS.md`](MCP_SERVER_REQUIREMENTS.md) — security + tool surface

## Package layout

```
tools/graphrag/
├── __init__.py
├── types.py              # Pydantic Node / Edge / ParseResult + enums
├── parsers/
│   ├── __init__.py
│   ├── base.py           # RepoParser Protocol + accepts_path()
│   └── markdown.py       # DocPage + DocSection
├── (forthcoming) edges.py        # cross-parser edge derivation (Phase 2)
├── (forthcoming) store/          # GraphClient Protocol + impl (Phase 3)
├── (forthcoming) retrieval/      # per-tool primitives (Phase 4)
├── (forthcoming) mcp_server.py   # stdio MCP wrapper (Phase 5)
├── (forthcoming) index.py        # CLI: full + incremental indexing (Phase 3)
├── (forthcoming) verify.py       # verification harness (Phase 6)
└── README.md             # this file
```

## How to run (once Phase 5 lands)

```bash
# one-time
uv pip install -e .[dev]

# index the repo (full or incremental)
python -m tools.graphrag.index --full

# start the MCP server (stdio; Claude Code launches via .mcp.json)
python -m tools.graphrag.mcp_server

# run verification (must pass before declaring gate #6 closed)
python -m tools.graphrag.verify
```

Today (Phase 0 / 1.1), only `pytest tests/graphrag/` works.

## How to extend

- **New parser**: add a module under `parsers/`. Export `ACCEPTS: tuple[str, ...]` + `parse(file_path, repo_root) -> ParseResult`. Register it in `parsers/__init__.py`. Add tests under `tests/graphrag/test_<parser>.py`.
- **New edge rule**: add to `edges.py` (Phase 2). One function per rule; pure.
- **New retrieval tool**: add to `retrieval/`. Update `tools/mcp/tools.md` with the signature.

## Sandbox + security

- Read-only by default (per `tools/mcp/security.md`).
- Sandbox = repo root.
- Never returns `.env` or `*.key` / `*.pem` / `*.secret` content.
- Logs every MCP tool call to `tools/graphrag/logs/mcp.jsonl`.

## License

Apache-2.0, like the rest of the repository code — see the root `LICENSE` and `NOTICE`.
