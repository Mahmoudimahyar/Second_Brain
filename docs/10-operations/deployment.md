# Deployment

> V1 = single workstation. V2 reopens for cloud / multi-tenant.

## Environments (V1)

| Environment | Where | Purpose |
|---|---|---|
| `local` | Mahyar's workstation (Windows 11, GTX 1080, 64 GB RAM) | Development, V1 ingestion sweeps, V1 HITL sessions, V1 retrieval consumption |
| `tests` | Same machine, pytest-managed temp dirs | CI + local test runs; isolated SQLite + graph-DB instances |
| `evals` | Same machine, `evals/` harnesses | Gold-set runs against frozen fixtures |

There is **no `staging` or `production` environment in V1**. V2 introduces those.

## Deployment platform (V1)

Local processes:

1. **Graph DB** — runs per the ADR-001 winner:
   - **LadybugDB**: embedded in the Python process. No separate service.
   - **Graphiti + Neo4j Community**: Neo4j 5.x via Docker (single container, single DB). Graphiti library loaded in the Python process.
   - **Postgres + AGE + pgvector**: Postgres 16 native install or Docker. Single DB. AGE + pgvector extensions enabled.
2. **SQLite side store** — file under `data/sqlite/engine.db`. Embedded.
3. **MCP servers** — two stdio processes:
   - `tools/graphrag/` — repo MCP (always running while Claude Code is active).
   - V1 product engine MCP — spawned on demand by V1 callers (HITL CLI, ad-hoc Python scripts, Claude Code if testing).
4. **HITL CLI** — `typer` app installed via `pip install -e .`. Invoked as `hitl pull`, `hitl commit`, etc.
5. **Extraction pipeline** — invoked as `python -m src.cli sweep ...` or via orchestrator (Prefect/Dagster/plain — ADR-010 deferred).
6. **Langfuse** — V1 default = local self-hosted Docker (private). Cloud Langfuse is acceptable if Mahyar prefers + accepts that LLM-call telemetry leaves the workstation.

## Build command (V1)

There is no compiled build in V1. The workflow is:

```bash
# initial setup
uv venv && source .venv/bin/activate     # or python -m venv .venv on Windows
uv sync                                   # or pip install -e .[dev]
cp .env.example .env                      # then fill in real keys

# graph DB (per ADR-001 winner)
docker compose up -d neo4j                # only if Graphiti+Neo4j won; else skip

# repo MCP context server (gate #6)
python tools/graphrag/index.py            # one-time + after schema changes
python tools/graphrag/mcp_server.py       # stdio MCP, kept running

# ingestion sweep (Phase 1+ of slice plan)
python -m src.cli ingest --source l5_reddit --subreddit DentalSchool

# HITL session
hitl pull
# (reviewer edits YAML)
hitl commit <item_id>

# retrieval (ad-hoc)
python -m src.cli query "top UCSF pain points 2023-2024"
```

A `Makefile` (or `justfile`) consolidates these into `make setup`, `make index-repo`, `make sweep`, `make hitl`, `make query`. Written during V1 implementation.

## Start command (V1)

There is no long-running "server" in V1 product engine (MCP is stdio, spawned by callers). Long-running things are:
- Docker Neo4j (if applicable).
- Local Langfuse (if running self-hosted).
- `tools/graphrag/` MCP server (started by Claude Code as a child process, configured via `.mcp.json`).

## Required environment variables

See `.env.example` (populated during the Environment Gate per `gates.md` §5; currently pending — `.env.example` writes happen once the bake-off + ADR-011 land and we know exact graph-DB + telemetry needs). High-confidence list:

```
# LLM vendors (gateway)
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GOOGLE_API_KEY=             # or VERTEX_PROJECT_ID + VERTEX_LOCATION for Vertex

# Telemetry
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=              # http://localhost:3000 if self-hosted

# Graph DB (only the relevant one set, per ADR-001 winner)
NEO4J_URI=                  # bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=
# or
POSTGRES_DSN=               # postgres://...

# Data paths
DATA_DIR=./data
EXTERNAL_DATA_DIR=./External Data

# Behavior flags
PROMPT_CACHE_TTL_SECONDS=3600    # enforced; never override
HITL_AUTO_ACCEPT_THRESHOLD=0.90
HITL_REJECT_THRESHOLD=0.75
```

## CI / verification

Per AGENTS.md "Done means done" + `gates.md`:
- **Local CI**: `make ci` runs ruff + mypy + pytest + ttl-lint + cost-regression. Must pass before commit.
- **No remote CI in V1.** V2 (when external users arrive) introduces GitHub Actions / equivalent.

## Backups (V1)

V1 lives on Mahyar's workstation. Backup strategy:
- `External Data\` is large (4.7 GB) and not changing fast — backed up to external drive (Mahyar's responsibility).
- `data/` is reproducible from `External Data\` + audit log + dump raw payloads; backup is nice-to-have, not critical.
- `data/sqlite/engine.db` is the only stateful artifact worth backing up; `data/dumps/` and the graph-DB data dir are reproducible.
- Suggested cadence: weekly snapshot of `data/sqlite/` to a cloud drive (manual or scheduled).

## Disaster recovery (V1)

If the workstation dies:
1. Reinstall Python + Docker + uv on a new machine.
2. Restore `External Data\` from backup.
3. Restore `data/sqlite/engine.db` from backup (if available).
4. If not available: re-run all ingest sweeps from raw `External Data\` — full re-sweep cost ≤ $80-$300 per `tech-stack.md`.

V1 recovery time objective: 1-2 days of Mahyar's wall-clock.

## V2 deployment plan (preview, deferred)

When the engine moves to external use:
- Containerization (one image per process kind: ingestion worker, retrieval MCP, HITL UI backend).
- Cloud provider TBD (AWS / GCP / Hetzner — license + cost-pattern-driven).
- Postgres + Neo4j or Kùzu-cloud (depending on ADR-001 winner's hosted-offering availability).
- Object store (S3 / R2) for immutable dumps.
- Backup + DR + multi-region considerations.
- CI/CD pipeline (GitHub Actions or equivalent).

V2 deployment doc will be a fresh file when V2 work begins.

## Observability hooks (V1)

- Langfuse for LLM calls.
- structlog for app logs (JSON to stderr + file).
- SQLite `audit_log` queryable via DuckDB or directly.
- Manual periodic review by Mahyar of sweep-summary reports under `/.agent/reports/`.

See `docs/13-observability/observability.md` for details (TBD next batch).
