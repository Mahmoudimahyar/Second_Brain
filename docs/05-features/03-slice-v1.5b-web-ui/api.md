# API — V1.5b

> FastAPI routes mounted at `/api/v1/*`. Pydantic models in `data.md` + V1.5a `data.md` + V1 retrieval API. Zod schemas auto-generated. Frontend consumes via TanStack Query hooks.

## Graph endpoints (per ADR-012)

```
GET  /api/v1/graph/structural?corpus={id}&query={q}&time_range={start},{end}&as_of={dt}&traversal_depth={n}
GET  /api/v1/graph/clusters?corpus={id}&time_range={start},{end}
GET  /api/v1/graph/analyzed?corpus={id}&query={q}&source_tier_min={tier}&time_range=...&as_of=...&traversal_depth={n}&include_anomalies={bool}
GET  /api/v1/graph/crosslinks?corpus={id}&source_tier_min={tier}&time_range=...&as_of=...
GET  /api/v1/graph/entity/{id}
GET  /api/v1/graph/search?q={query}&corpus={id}&limit={n}
GET  /api/v1/graph/path?from={id}&to={id}&max_depth={n}
```

Each returns the corresponding `Level*Result` per `data.md`. p95 budgets per ADR-012 + `docs/08-ui/graph-level-views.md`.

## HITL endpoints

```
GET    /api/v1/hitl/inbox                     # counts per item_type
GET    /api/v1/hitl/items?item_type={t}&status={s}&limit={n}&claim={bool}
GET    /api/v1/hitl/items/{id}                # full item payload
POST   /api/v1/hitl/items/{id}/claim
POST   /api/v1/hitl/items/{id}/commit         # body = decision
POST   /api/v1/hitl/items/{id}/escalate
POST   /api/v1/hitl/items/{id}/defer
POST   /api/v1/hitl/items/batch/commit        # bulk-action endpoint
GET    /api/v1/hitl/history?from={dt}&to={dt}&item_type={t}
GET    /api/v1/hitl/history/{id}              # replay one decision
```

## Cluster-review-specific

```
GET  /api/v1/clusters?corpus={id}&status={pending|approved|culled}
POST /api/v1/clusters/review/batch            # body = ClusterReviewBatch
GET  /api/v1/clusters/{id}                    # detail + sample posts + status
POST /api/v1/clusters/{id}/merge              # body = {target_id}
POST /api/v1/clusters/{id}/split              # body = {n_targets}
```

## Proposal-review-specific

```
GET  /api/v1/proposals?corpus={id}&template_id={t}&status={pending|reviewed}
POST /api/v1/proposals/{id}/decide            # body = ProposalDecision
GET  /api/v1/proposals/{id}/context-preview   # show how this would affect the next context block
```

## Feedback-loop endpoints

```
GET  /api/v1/feedback-log?corpus={id}&template_id={t}&from={dt}&to={dt}&limit={n}
GET  /api/v1/feedback-loop/policy?corpus={id}&template_id={t}
PATCH /api/v1/feedback-loop/policy            # body = FeedbackLoopPolicy (partial)
GET  /api/v1/feedback-loop/context?corpus={id}&template_id={t}    # preview current context block
GET  /api/v1/feedback-loop/blocklist?corpus={id}&template_id={t}
POST /api/v1/feedback-loop/blocklist/{entry_id}/remove
```

## Audit endpoints

```
GET  /api/v1/audit?from={dt}&to={dt}&kind={k}&actor={a}&corpus={c}&source={s}&limit={n}
GET  /api/v1/audit/{id}
```

## Settings endpoints

```
GET    /api/v1/settings/corpora
GET    /api/v1/settings/extraction
PATCH  /api/v1/settings/extraction
GET    /api/v1/settings/feedback-loop
PATCH  /api/v1/settings/feedback-loop
```

## System endpoints

```
GET  /api/v1/health                           # backend + DB + Prefect server health
GET  /api/v1/health/llm                       # gateway health-check per vendor
POST /api/v1/dev/orchestrator/restart         # dev-only; re-spawns Prefect/uvicorn
```

## Error envelopes

All errors return RFC-7807-style:
```
{
  "type": "https://errors.secbrain.local/INVALID_TIER_UPGRADE",
  "title": "L1 upgrade requires confirmation",
  "status": 400,
  "detail": "...",
  "instance": "/api/v1/sources/ds:postgres:foo",
  "context": {...item-specific...}
}
```

## Authentication

V1.5: none. Backend binds `127.0.0.1`. UI runs from `localhost:3000`. Server rejects requests with `Origin` header outside localhost.

V2: NextAuth session → JWT → per-tenant scoping. Routes gain `/t/{tenant}/` prefix.

## Versioning

Path-versioned (`/api/v1`). V2 introduces `/api/v2` alongside; V1 stays available during transition.

## OpenAPI

FastAPI auto-generates `/openapi.json`. Served at `/api/v1/docs` (Swagger UI) — dev convenience only, localhost only.

## Type-bridge

Pydantic models live in `src/web/schemas/`. Pre-build step runs `make generate-types`:

```
make generate-types
  └─► datamodel-code-generator --input src/web/schemas/ --output web/src/lib/api/generated/python_types.ts
  └─► pydantic-to-zod ...    --output web/src/lib/api/generated/zod_schemas.ts
```

CI gate: `make check-types` runs the generators in `--check` mode; build fails on drift.

## TanStack Query hooks (frontend convention)

```
// web/src/lib/api/client.ts
import { useQuery, useMutation } from '@tanstack/react-query';
export const useStructuralGraph = (params: StructuralParams) =>
  useQuery({ queryKey: ['graph','structural', params], queryFn: ...});
export const useCommitClusterBatch = () =>
  useMutation({ mutationFn: (batch: ClusterReviewBatch) => ... });
```

Cache invalidation rules:
- Cluster batch commit → invalidates `['graph','clusters']` + `['hitl','inbox']`.
- Proposal decision → invalidates `['proposals']` + `['feedback-loop','context', template_id]`.
- Feedback-loop policy update → invalidates `['feedback-loop','context', *]`.
- Pull-delta success → invalidates `['sources', id]` + `['graph', *]`.

## Audit-log writes (server-side)

Every route writes one `audit_log` row (server-side) with the appropriate `kind`. Client doesn't write audit; the server does. Page-view events come from a tiny `useAuditPageView()` hook on the client that POSTs `/api/v1/audit/view` once per route mount.
