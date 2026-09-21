# Site Map — V1.5

> Replaces V1 TBD scaffold. V1.5 is single-user local: no auth, no public surfaces, no admin separation. The "internal" column reflects that all pages are operator-only by deployment posture.

## Public pages

| Route | Page | Purpose | Primary CTA |
|---|---|---|---|
| (none) | — | V1.5 ships no public-facing pages. Backend binds to `127.0.0.1`; UI loads from `http://localhost:3000` only. | — |

## Authenticated pages

| Route | Page | Purpose | Required role |
|---|---|---|---|
| (none) | — | V1.5 has no auth (V1.5-R1 Q12). All pages are reachable without login by virtue of localhost binding. V2 adds role-based access. | — |

## Operator / internal pages (V1.5 — every page)

### Top-level nav

| Section | Route | Purpose |
|---|---|---|
| Home | `/` | Landing — last-pull summary across all connectors, HITL inbox count, graph stats at a glance |
| Ingest | `/ingest` | All ingestion management |
| HITL | `/hitl` | All human-in-the-loop review queues |
| Graph | `/graph` | Three-level graph viewers + entity search |
| Teams | `/teams` | Per-team dashboards (PM / Social / Marketing) |
| Audit | `/audit` | Audit log viewer |
| Settings | `/settings` | Corpora, extraction config, providers, feedback-loop policy |

### Full route tree

```
/
├── ingest/
│   ├── (index — list of all sources)
│   ├── new/
│   │   ├── (index — engine picker)
│   │   ├── postgres
│   │   ├── mysql
│   │   ├── sqlite
│   │   ├── neo4j
│   │   ├── upload
│   │   └── [engine]/discover
│   │   └── [engine]/mapping
│   └── sources/
│       └── [id]/
│           ├── (index — connector dashboard)
│           ├── edit
│           └── disconnect
├── hitl/
│   ├── (index — inbox with counts per type)
│   ├── alias
│   ├── conflict
│   ├── clusters
│   ├── proposals
│   ├── multi-l1
│   ├── crosslinks
│   ├── judge
│   ├── escalated
│   └── history
├── graph/
│   ├── (index — view-picker / last-viewed)
│   ├── structural
│   ├── clusters
│   ├── analyzed
│   ├── entity/[id]
│   └── search
├── teams/
│   ├── (index — picker)
│   ├── pm/
│   │   ├── (index)
│   │   └── [id]
│   ├── social/
│   │   ├── (index)
│   │   └── topic/[id]
│   └── marketing/
│       ├── (index)
│       └── gap/[id]
├── audit/
│   ├── (index — filterable log)
│   └── [id]
├── settings/
│   ├── (index — section picker)
│   ├── corpora
│   ├── extraction
│   ├── web-search
│   └── feedback-loop
└── (system pages)
    ├── _not-found (404)
    ├── _error (500)
    ├── maintenance (V2)
    └── loading.tsx (per route)
```

## Navigation rules

- Sidebar persistent (collapsible). Highlights current section + sub-page.
- Breadcrumbs on every nested page (e.g., `Ingest › Sources › my-postgres-db › Edit`).
- Cmd/Ctrl-K opens command palette (jump to any route + entity search via `query_graph_search`).
- Cmd/Ctrl-1 / 2 / 3 jump between the three graph views (Level A / B / C) when in `/graph/*`.

## V1.5 → V2 reframe

When V2 multi-tenant lands, this site map gains:

- `/login` and `/signup` public pages.
- Per-tenant scoping: `/teams/pm` becomes `/t/[tenant]/teams/pm`.
- Admin: `/admin/users`, `/admin/audit`, `/admin/tenants`.
- All operator pages move under `/(auth)/` group with NextAuth session enforcement.

V1.5 routes are designed to be drop-in compatible: when the auth wrapper lands, the per-tenant prefix becomes mandatory but the post-prefix paths don't change.
