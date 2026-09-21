# SecBrain V1.5b Web

Next.js 15 + React 19 + Tailwind 4 + shadcn primitives + TanStack Query.

## Bootstrap (one-time)

```
cd web
pnpm install
```

Requires Node 22+ and pnpm 11+.

## Dev

```
secbrain ui                    # boots FastAPI (port 8000) + Next dev (port 3000) + opens browser
```

Or run each leg separately:

```
# Backend
uvicorn src.web.app:create_app --factory --reload --port 8000

# Frontend
cd web && pnpm dev
```

The frontend proxies `/api/v1/*` to `NEXT_PUBLIC_API_BASE` (default
`http://127.0.0.1:8000`). Set the env var if you run the backend elsewhere.

## Page structure (41 `page.tsx` routes today; plan in `docs/08-ui/page-inventory.md`)

```
/                              # Home
/ingest                        # Sources index
/ingest/new                    # Engine picker
/ingest/new/{engine}           # Per-engine config (Postgres lives; others stub)
/ingest/sources/{id}           # Connector dashboard

/hitl                          # Inbox
/hitl/alias                    # Alias review
/hitl/conflict                 # Conflict review
/hitl/clusters                 # Cluster-cull review
/hitl/proposals                # Node/edge proposal review
/hitl/multi-l1                 # Multi-L1 collision
/hitl/crosslinks               # Cross-graph link review
/hitl/judge                    # Judge disagreement
/hitl/escalated                # Escalated queue
/hitl/history                  # Read-only history

/graph                         # View picker
/graph/structural              # Level A
/graph/clusters                # Level B
/graph/analyzed                # Level C

/teams                         # Per-team picker (V1.5c)
/teams/pm
/teams/social
/teams/marketing

/audit                         # Audit log viewer

/settings/feedback-loop        # Active context + blocklist (ADR-018)
/settings/corpora              # Corpora listing
/settings/web-search           # V1.5c surface
```

## Testing (V1.5b Phase 7)

```
pnpm typecheck         # tsc --noEmit
pnpm test              # Vitest unit
pnpm test:e2e          # Playwright (requires `pnpm exec playwright install`)
```

axe-core integration is wired into `tests/e2e/*` once Playwright is up.

## V1.5b scope status

Backend: complete (FastAPI mount + 5 routers + feedback loop + level
filters per ADR-012). See `.agent/reports/v1.5b-slice.md` for the
verification report.

Frontend: scaffolded (app shell + all page routes structurally
present; vertical-slice pages — Postgres + SQLite connect forms,
connector dashboard, HITL inbox + per-type review pages, three graph
views, feedback-loop settings, audit log — fully wired to FastAPI).
Sigma.js WebGL canvas + full per-engine forms + per-team dashboards are
the remaining V1.5b polish + V1.5c work.
