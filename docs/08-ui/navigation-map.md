# Navigation Map — V1.5

> Replaces V1 TBD scaffold. Maps every V1.5 route to its feature, auth requirements, and primary entry/exit transitions.

## Auth — uniform across V1.5

All routes are single-user local, no auth (V1.5-R1 Q12). UI binds `localhost:3000` → FastAPI at `127.0.0.1:8000`. V2 introduces NextAuth + per-tenant prefix.

## Route → feature → transitions

| Route | Page | Feature | Entry from | Common exits |
|---|---|---|---|---|
| `/` | Home | V1.5b | direct, sidebar | `/ingest`, `/hitl`, `/graph/clusters` |
| `/ingest` | Sources index | V1.5a | sidebar, `/` quicklink | `/ingest/new`, `/ingest/sources/[id]` |
| `/ingest/new` | Engine picker | V1.5a | `/ingest`, command palette | `/ingest/new/[engine]` |
| `/ingest/new/postgres` | Postgres config | V1.5a | `/ingest/new` | `/ingest/new/postgres/discover` (on connect-success), error toast (on fail) |
| `/ingest/new/[engine]/discover` | Schema discovery | V1.5a | `/ingest/new/[engine]` | `/ingest/new/[engine]/mapping` (on accept) |
| `/ingest/new/[engine]/mapping` | Mapping wizard | V1.5a | discover step | `/ingest/sources/[id]` (on commit), back to discover |
| `/ingest/sources/[id]` | Connector dashboard | V1.5a + V1.5b | `/ingest`, command palette | `/ingest/sources/[id]/edit`, `/hitl/crosslinks`, `/graph/analyzed?source=[id]` |
| `/ingest/sources/[id]/edit` | Connector edit | V1.5a | dashboard | dashboard (on save) |
| `/ingest/sources/[id]/disconnect` | Disconnect | V1.5a | dashboard | `/ingest` (on confirm) |
| `/hitl` | Inbox | V1.5b | sidebar, `/` | `/hitl/[type]` |
| `/hitl/alias` | Alias review | V1.5b | inbox | next-item or `/hitl` (on empty) |
| `/hitl/conflict` | Conflict review | V1.5b | inbox | next-item, `/graph/analyzed?entity=[id]` for context, `/hitl/escalated` (escalate) |
| `/hitl/clusters` | Cluster cull | V1.5b | inbox, `/graph/clusters` | `/graph/clusters` (after batch commit) |
| `/hitl/proposals` | Node/edge proposal review | V1.5b | inbox | next-item, `/settings/feedback-loop` (view applied blocklist) |
| `/hitl/multi-l1` | Multi-L1 collision | V1.5a | inbox | `/ingest/sources/[id]` (for context) |
| `/hitl/crosslinks` | Cross-graph link review | V1.5a | inbox | `/graph/analyzed?entity=[id]` for evidence |
| `/hitl/judge` | Judge disagreement | V1 (carried) | inbox | next-item |
| `/hitl/escalated` | Escalated queue | V1.5b | inbox, "escalate" from any review | per-item decision |
| `/hitl/history` | Read-only history | V1.5b | inbox | per-decision replay |
| `/graph` | Graph view picker | V1.5b | sidebar | `/graph/structural`, `/graph/clusters`, `/graph/analyzed` |
| `/graph/structural` | Level A | V1.5b (ADR-012) | `/graph`, Cmd-1, command palette | `/graph/clusters` (Cmd-2), `/graph/entity/[id]` (on node click) |
| `/graph/clusters` | Level B | V1.5b (ADR-012) | `/graph`, Cmd-2 | `/graph/analyzed` (Cmd-3), `/hitl/clusters` (on review action) |
| `/graph/analyzed` | Level C | V1.5b (ADR-012) | `/graph`, Cmd-3 | `/graph/entity/[id]`, citation drawer to source rows |
| `/graph/entity/[id]` | Entity detail | V1.5b | any graph view click, `/graph/search` | back to whichever view referred |
| `/graph/search` | Entity search | V1.5b | Cmd-K, top bar | `/graph/entity/[id]` |
| `/teams` | Team picker | V1.5c | sidebar | `/teams/pm`, `/teams/social`, `/teams/marketing` |
| `/teams/pm` | PM dashboard | V1.5c | `/teams`, sidebar | `/teams/pm/[id]`, `/graph/analyzed?entity=[id]` |
| `/teams/pm/[id]` | Pain-point detail | V1.5c | `/teams/pm` | back, source citations open in `/graph/analyzed` |
| `/teams/social` | Social dashboard | V1.5c | `/teams` | `/teams/social/topic/[id]` |
| `/teams/social/topic/[id]` | Topic trend detail | V1.5c | `/teams/social` | back, source posts in `/graph/analyzed` |
| `/teams/marketing` | Marketing dashboard | V1.5c | `/teams` | `/teams/marketing/gap/[id]` |
| `/teams/marketing/gap/[id]` | Content gap detail | V1.5c | `/teams/marketing` | back, source data in `/graph/analyzed` |
| `/audit` | Audit log | V1.5b | sidebar | `/audit/[id]` |
| `/audit/[id]` | Audit entry | V1.5b | `/audit` | back |
| `/settings/corpora` | Corpora | V1.5b | `/settings` | `/ingest/sources/[id]` |
| `/settings/extraction` | Extraction config | V1.5b | `/settings` | save |
| `/settings/web-search` | Web-search providers | V1.5c | `/settings` | save, health-check |
| `/settings/feedback-loop` | Feedback-loop policy | V1.5b | `/settings`, `/hitl/proposals` | save |

## Common interaction patterns

**Drill-down chain (most-used flow)**:

```
/teams/pm  →  /teams/pm/[pain_point_id]  →  /graph/analyzed?entity=[anchor_id]
   (PM picks    (Detail page shows                 (Full analyzed graph
    a pain       supporting forum posts +           centered on the anchor;
    point)       proposed feature angles +          citations clickable back
                 source citations)                  to source rows)
```

**HITL review chain (per item type)**:

```
/hitl  →  /hitl/[type]  →  per-item decision UI  →  commit
                       └─►  next-item OR back to /hitl (on empty)
                       └─►  /hitl/escalated (if user escalates)
```

**Ingestion chain (V1.5a + V1.5b)**:

```
/ingest  →  /ingest/new  →  /ingest/new/[engine]  →  /ingest/new/[engine]/discover
        →  /ingest/new/[engine]/mapping  →  /ingest/sources/[id]
        →  (HITL queue fills with crosslinks + multi-L1 items if any)
        →  /hitl/crosslinks  →  back to /ingest/sources/[id]
```

**Cluster-cull + propose loop (V1.5b)**:

```
/graph/clusters  →  user culls clusters via batch toolbar  →  commit batch
              →  /hitl/proposals (new proposals from approved clusters' Pass 4)
              →  per-proposal decision  →  next Pass 4 runs with updated context
```

## Page-load gates

- `/ingest/new/[engine]/discover` blocks rendering until the schema-discovery request returns. Renders skeleton until.
- `/graph/clusters` requires Pass 3 to have completed at least once for the corpus; otherwise renders empty state with CTA "Run Pass 3 first."
- `/teams/*` requires Pass 4 to have completed at least once on at least one cluster; otherwise empty state.
- `/hitl/[type]` always loads (empty state is acceptable).
