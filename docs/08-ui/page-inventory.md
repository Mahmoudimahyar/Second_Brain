# Page Inventory — V1.5

> Replaces the V1 TBD scaffold. Authoritative list of pages V1.5b ships. Routes match `docs/11-decisions/ADR-013-ui-tech-stack.md` directory layout.

## Ingestion

| Page | Route | Feature | States required | E2E test required? |
|---|---|---|---|---|
| Ingestion home | `/ingest` | V1.5a + V1.5b | happy / loading / empty (no sources yet) | Yes |
| New source — pick engine | `/ingest/new` | V1.5a | happy / loading | Yes |
| New source — Postgres config | `/ingest/new/postgres` | V1.5a | happy / loading / error (connect failed) / cred-required | Yes |
| New source — MySQL config | `/ingest/new/mysql` | V1.5a | same shape | Yes |
| New source — SQLite config | `/ingest/new/sqlite` | V1.5a | same shape | Yes |
| New source — Neo4j config | `/ingest/new/neo4j` | V1.5a | same shape | Yes |
| New source — file upload (Excel / PDF / CSV / JSONL) | `/ingest/new/upload` | V1.5a + V1 wrap | happy / drag-drop / parse error | Yes |
| Schema discovery preview | `/ingest/new/[engine]/discover` | V1.5a | happy / loading (with progress) / error | Yes |
| Mapping wizard | `/ingest/new/[engine]/mapping` | V1.5a | happy / loading (suggesting) / per-row edit / commit-progress | Yes |
| Connector dashboard | `/ingest/sources/[id]` | V1.5a + V1.5b | happy / paused / errored / pulling-now / last-pull-summary | Yes |
| Connector edit | `/ingest/sources/[id]/edit` | V1.5a | happy / mapping-changed-confirm / tier-change-warning | Yes |
| Connector disconnect | `/ingest/sources/[id]/disconnect` | V1.5a | confirm-modal / soft-delete-progress / done | Yes |

## HITL review

| Page | Route | Feature | States required | E2E test required? |
|---|---|---|---|---|
| HITL inbox | `/hitl` | V1.5b | happy (with counts per type) / empty / loading | Yes |
| Alias review | `/hitl/alias` | V1.5b | happy / loading / next-item / batch-mode | Yes |
| Conflict review | `/hitl/conflict` | V1.5b | happy / loading / next-item / L1-clash-detail | Yes |
| Cluster-cull review | `/hitl/clusters` | V1.5b | happy / loading / cluster-detail / merge-target-picker / split-form | Yes |
| Node/edge proposal review | `/hitl/proposals` | V1.5b | happy / loading / per-proposal-detail / blocklist-confirm | Yes |
| Multi-L1 collision review | `/hitl/multi-l1` | V1.5a + V1.5b | happy / per-conflict-detail / pick-winner | Yes |
| Cross-graph link review | `/hitl/crosslinks` | V1.5a + V1.5b | happy / per-link-detail / side-by-side-evidence | Yes |
| Judge-disagreement review | `/hitl/judge` | V1 + V1.5b | happy / detail / 3-vendor breakdown | Yes |
| Escalation queue | `/hitl/escalated` | V1.5b | happy / detail / commit / re-escalate | Yes |
| HITL history (read-only) | `/hitl/history` | V1.5b | happy / loading / per-decision-replay | Yes |

## Graph views

| Page | Route | Feature | States required | E2E test required? |
|---|---|---|---|---|
| Level A — structural | `/graph/structural` | V1.5b (ADR-012) | happy / loading / empty / node-selected / multi-select | Yes |
| Level B — clusters | `/graph/clusters` | V1.5b (ADR-012) | happy / loading / empty / cluster-selected / review-batch-mode | Yes |
| Level C — analyzed | `/graph/analyzed` | V1.5b (ADR-012) | happy / loading / empty / node-selected / path-finder / citation-drawer | Yes |
| Entity detail (deep-link) | `/graph/entity/[id]` | V1.5b | happy / loading / not-found | Yes |
| Query/search results | `/graph/search?q=...` | V1.5b | happy / loading / empty / multi-result | Yes |

## Per-team dashboards (V1.5c)

| Page | Route | Feature | States required | E2E test required? |
|---|---|---|---|---|
| PM dashboard | `/teams/pm` | V1.5c | happy / loading / empty / drill-down to entity | Yes |
| PM — pain-point detail | `/teams/pm/[id]` | V1.5c | happy / loading / source citations / suggested feature angles | Yes |
| Social-media dashboard | `/teams/social` | V1.5c | happy / loading / trending-now / time-window picker / suggested-post panel | Yes |
| Social — topic detail | `/teams/social/topic/[id]` | V1.5c | happy / loading / trend chart / sentiment timeline / source posts | Yes |
| Marketing/SEO dashboard | `/teams/marketing` | V1.5c | happy / loading / content-gap matrix / positioning view | Yes |
| Marketing — gap detail | `/teams/marketing/gap/[id]` | V1.5c | happy / loading / supporting data / suggested content angles | Yes |

## System / audit / settings

| Page | Route | Feature | States required | E2E test required? |
|---|---|---|---|---|
| Audit log viewer | `/audit` | V1.5b | happy / loading / filtered / time-range picker | Yes |
| Audit log entry detail | `/audit/[id]` | V1.5b | happy / loading / not-found | Yes |
| Settings — corpora | `/settings/corpora` | V1.5b | happy / per-corpus-summary | Yes |
| Settings — extraction config | `/settings/extraction` | V1.5b | happy / per-pass tuning | No (V1.5 read-mostly) |
| Settings — web-search providers | `/settings/web-search` | V1.5c | happy / API-key entry / health-check | Yes |
| Settings — feedback-loop policy | `/settings/feedback-loop` | V1.5b | happy / blocklist viewer / context-block viewer | Yes |

## System pages (Next.js conventions)

| Page | Route | Notes |
|---|---|---|
| 404 | (catch-all) | Brand-consistent, links to `/` |
| 500 | (error boundary) | Logs the error to backend `/api/v1/errors`, links to audit log |
| Loading | `loading.tsx` per route | Skeleton-screen variant matching the page |
| Empty state | inline per page | Per `EmptyState` component spec |
| Maintenance | `/maintenance` | Manual flag toggle (V1.5b nice-to-have; V2 mandatory) |

## Page-count summary

- Ingestion: 11 pages
- HITL: 10 pages
- Graph: 5 pages
- Per-team: 6 pages
- System / audit / settings: 6 pages
- **Total: 38 pages**, of which 5 are dynamic-route detail pages.

E2E test coverage gate (NFR carried from V1): every E2E-required page has at least one Playwright smoke test passing. Per V1.5b's plan, the first vertical slice exercises 4 pages (ingest/new/postgres → discover → mapping → connector dashboard) before broad implementation.
