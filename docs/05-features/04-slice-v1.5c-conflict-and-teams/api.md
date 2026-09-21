# API — V1.5c

> Extends V1.5b. New routes for web-verification + per-team dashboards + web-search settings.

## Web-verification endpoints

Usually invoked internally by the conflict resolver, but exposed for HITL replay + manual verification:

```
POST /api/v1/web-verify/verify              # body = VerifyClaimRequest; returns VerdictResult
GET  /api/v1/web-verify/runs?corpus={id}&from={dt}&to={dt}&verdict={v}
GET  /api/v1/web-verify/runs/{run_id}
POST /api/v1/web-verify/runs/{run_id}/replay  # re-runs the verification (bypasses cache)
GET  /api/v1/web-verify/cost?corpus={id}&from={dt}&to={dt}
GET  /api/v1/web-verify/cost/cap?corpus={id} # current cap + spend
PATCH /api/v1/web-verify/cost/cap            # body = {corpus_id, cap_usd}
POST /api/v1/web-verify/cost/reset?corpus={id} # manual unfreeze after cap_hit
GET  /api/v1/web-verify/health               # Tavily key health-check
```

## Per-team dashboard endpoints

### PM
```
GET  /api/v1/teams/pm?corpus={id}&audience_segment={s}&time_range=...&min_volume={n}&sort_by={volume|sentiment|trend}
GET  /api/v1/teams/pm/{id}                  # PainPointDetail (with citations)
GET  /api/v1/teams/pm/{id}/angles?k={3}     # SuggestedAngles (LLM-generated, lazy)
```

### Social
```
GET  /api/v1/teams/social?corpus={id}&window={24h|7d|30d|90d}&min_volume={n}&sentiment_band={neg|neu|pos}
GET  /api/v1/teams/social/topic/{id}        # TopicTrendDetail
GET  /api/v1/teams/social/topic/{id}/angles?k={3}
```

### Marketing
```
GET  /api/v1/teams/marketing?corpus={id}&category={c}&min_volume={n}&sentiment_threshold={f}
GET  /api/v1/teams/marketing/gap/{id}       # ContentGapDetail
GET  /api/v1/teams/marketing/gap/{id}/angles?k={3}
```

### Shared
```
POST /api/v1/teams/rollups/refresh?team={t}&corpus={id}  # manual rollup recomputation
```

## Web-search settings endpoints

```
GET    /api/v1/settings/web-search
PATCH  /api/v1/settings/web-search          # body = WebSearchSettings
POST   /api/v1/settings/web-search/health   # runs tavily.qna_search('ping')
GET    /api/v1/settings/web-search/usage?corpus={id}&days={n}
```

## HITL extensions (item types added by V1.5c)

V1.5c uses the existing V1.5b HITL endpoints (`POST /api/v1/hitl/items/{id}/commit`) but introduces two new item types renderable through them:
- `web_search_disagreement` — payload includes the three signal results
- `tavily_unavailable` — payload includes original claim + retry options

## Pydantic schemas

Per `data.md`. Zod schemas generated via the same `make generate-types` pipeline as V1.5b.

## Error envelopes (V1.5c-specific)

- `TAVILY_UNAVAILABLE` (503) — Tavily failed after 3 retries
- `WEB_SEARCH_CAP_HIT` (429) — per-corpus cap reached
- `INVALID_CAP` (400) — cap value out of range
- `ROLLUP_STALE` (200 with `warning` header) — rollup data > 24h old; user sees banner

## Authentication

V1.5: none (localhost only). V2 multi-tenant adds session scoping.

## Versioning

Path-versioned (`/api/v1`). V2 introduces `/api/v2` alongside.

## Audit-log writes

Every endpoint writes one `audit_log` row server-side with the appropriate `kind`. `web_search_call` written for each underlying Tavily/LLM call; `web_verify_verdict` written for each verdict; `team_dashboard_view` written for each team-page load; `team_angles_generated` written for each angle-suggestion call.

## TanStack Query hooks

```
useVerifyClaim()                                # mutation; rare, mostly manual replay
useWebVerifyRuns(filters)                       # query
useTeamPM(filters)                              # query
useTeamSocial(filters)                          # query
useTeamMarketing(filters)                       # query
useSuggestedAngles({team, item_id, k})          # query; cached
useWebSearchSettings()                          # query
usePatchWebSearchSettings()                     # mutation
useWebSearchUsage(corpus_id, days)              # query
```

Cache invalidation:
- Team page filters change → invalidates the team's list-page query.
- Manual rollup refresh → invalidates all team queries for the affected team + corpus.
- Web-verify cap reset → invalidates the cap + usage queries.

## Prefect flow endpoints (internal)

```
flows/team_rollups.py
  schedule: daily at 03:00 local
  per team × per corpus, compute rollup, write to team_rollups, audit-log

flows/web_search_cap_reset.py
  schedule: weekly at Monday 00:00 local
  reset per-corpus caps for the upcoming sweep window
```

## Browser validation

Per CLAUDE.md "UI changes use browser automation and check console/network errors": every endpoint touched by a UI page has a Playwright E2E test that asserts the network request shape + response shape end-to-end, plus a console-error gate.
