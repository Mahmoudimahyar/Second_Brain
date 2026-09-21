# Hero Page Designs — Full Specs

> Page-level designs for the six most-used flows. Each section provides: purpose, layout sketch, components used, interactions, edge cases, accessibility.

The six hero pages:

1. **Home** (`/`) — operational dashboard, the user's daily entry point.
2. **Ingestion wizard — Postgres** (`/ingest/new/postgres` + discover + mapping) — the canonical journey.
3. **Cluster cull review** (`/hitl/clusters`) — the highest-value HITL flow.
4. **Conflict review** (`/hitl/conflict`) — the trust-tier-aware decision UI.
5. **Level C graph view** (`/graph/analyzed`) — the full analyzed surface.
6. **PM dashboard** (`/teams/pm`) — the per-team payoff.

---

## 1. Home (`/`)

### Purpose

The user opens this every morning. They want to know: what's in the inbox, what's running, what was ingested last, are there warnings.

### Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│ [Sidebar]  [TopBar: corpus / time / search / theme]                 │
├─────────────────────────────────────────────────────────────────────┤
│  Welcome back, Mahyar.                  Last sweep: 2 hours ago     │
│  ────────────────────────────────────────────────────────────────  │
│                                                                     │
│  ┌─ HITL inbox ──────────────┐  ┌─ Running now ──────────────┐    │
│  │  ●  3 alias               │  │  Pulling r/DentalSchool    │    │
│  │  ●  2 conflicts            │  │  Pass 4 · 62% · 3m left    │    │
│  │  ●  18 clusters to review  │  │  $0.11 / $0.50             │    │
│  │  ●  7 proposals            │  │  [View detail →]            │    │
│  │  ●  1 multi-L1             │  └────────────────────────────┘    │
│  │  ●  5 cross-links          │                                    │
│  │  [Review →]                │  ┌─ Recent activity ─────────┐    │
│  └─────────────────────────────┘  │  ✓ Cluster commit (16)   │    │
│                                    │  ✓ Proposal accept (3)   │    │
│  ┌─ Graph state ──────────────┐   │  ✓ Conflict resolved (1) │    │
│  │  Nodes:        38,037      │   │  ✓ Source added (1)      │    │
│  │  Edges:        71,121      │   │  [View audit log →]      │    │
│  │  L1 anchors:      124      │   └──────────────────────────┘    │
│  │  Cross-links:      53      │                                    │
│  │  [Open graph →]            │   ┌─ Top open questions ─────┐    │
│  └─────────────────────────────┘   │  3 high-volume pain pts  │    │
│                                    │  unresolved in PM dash   │    │
│  ┌─ Cost (last 7d) ───────────┐   │  [Open PM dash →]        │    │
│  │  ▁▂▃▅▇▆▅ $4.32 total       │   └──────────────────────────┘    │
│  │  By task: sentiment $1.7   │                                    │
│  │  ... [chart]               │   ┌─ Sources ─────────────────┐   │
│  └─────────────────────────────┘   │  ✓ ADEA L1                │   │
│                                    │  ✓ r/DentalSchool L5      │   │
│                                    │  ◐ Partner DB (pulling)   │   │
│                                    │  [+ Connect new source]   │   │
│                                    └───────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Components used

- `KpiCard` (Tremor) for the six summary cards.
- `ProgressStreamCard` for "Running now."
- `BarChart` (Tremor) for cost trend.
- `Timeline` (custom) for recent activity.
- `EmptyState` if all queues are empty (rare).

### Interactions

- Click any HITL count → opens that queue.
- Click "View detail" on running → opens connector dashboard.
- Click "Open graph" → opens Level C with the most-recent corpus.
- Hover the cost chart → tooltip with daily breakdown.

### Animation

- Cards stagger-fade on first load (100ms each).
- KPI numbers count up from 0 over 600ms (Magic UI's `NumberTicker`).
- Recent activity rows slide in from the top when new audit events stream.

### Edge cases

- All-empty (just-installed): show onboarding with "Connect your first source" prominent CTA. Hide all other panels.
- Multiple running pulls: stack `ProgressStreamCard`s vertically.
- HITL inbox very deep (> 50 items): show "lots to review" prompt with a "Help me prioritize" button (opens a triage view).

---

## 2. Ingestion wizard — Postgres journey

### Three pages, one flow

`/ingest/new/postgres` → `/ingest/new/postgres/discover` → `/ingest/new/postgres/mapping` → `/ingest/sources/{id}`

### Page 1 — Connection (`/ingest/new/postgres`)

```
┌───────────────────────────────────────────────────────────────────┐
│  Ingest › New source › Postgres                                   │
│  ┌─ JourneyRail ────────────────────────────────────────────────┐│
│  │  ● Intake  ○ Discover  ○ Process  ○ Verify  ○ Live           ││
│  └───────────────────────────────────────────────────────────────┘│
│                                                                   │
│  ┌─ Form ─────────────────────┐  ┌─ Preview ─────────────────┐  │
│  │  Display name              │  │  What this connector will │  │
│  │  [Partner ADEA DB        ] │  │  do                       │  │
│  │                            │  │                           │  │
│  │  Host                      │  │  1. List your tables and  │  │
│  │  [partner-db.example.com ]│  │     sample 100 rows each. │  │
│  │                            │  │                           │  │
│  │  Port                      │  │  2. Suggest how each      │  │
│  │  [5432                  ]  │  │     table maps to a Node  │  │
│  │                            │  │     or Edge.              │  │
│  │  Database                  │  │                           │  │
│  │  [adea_partner          ]  │  │  3. You approve mappings  │  │
│  │                            │  │     (high-conf auto;      │  │
│  │  User                      │  │     low-conf reviewed).   │  │
│  │  [readonly_user         ]  │  │                           │  │
│  │                            │  │  4. Pull deltas on the    │  │
│  │  Password (env var ref)    │  │     schedule (default     │  │
│  │  [PARTNER_DB_PASSWORD   ] │  │     daily).               │  │
│  │  ⚠ V1.5 stores credentials │  │                           │  │
│  │    in plaintext .env       │  │  Est. time: ~2 min for    │  │
│  │                            │  │  a typical 50-table DB.  │  │
│  │  SSL mode                  │  └───────────────────────────┘  │
│  │  [prefer ▾]               │                                  │
│  │                            │  ┌─ Tier ────────────────────┐  │
│  │  Schema filter             │  │  Tier  [L2 ▾]             │  │
│  │  [public                ] │  │  L2 is the default for     │  │
│  │                            │  │  external DBs. Upgrade to  │  │
│  │  [Test connection]         │  │  L1 (canonical truth) only │  │
│  │  ✓ Connected (24ms)        │  │  if this data is immutable │  │
│  │                            │  │  ground truth.             │  │
│  │  [← Cancel] [Continue →]   │  └───────────────────────────┘  │
│  └────────────────────────────┘                                  │
└───────────────────────────────────────────────────────────────────┘
```

**Components**: `JourneyRail`, `Form` (shadcn + react-hook-form), `CredentialField`, `TierSelector`, animated preview list.

**Animation**: Preview list items animate in on first render (Aceternity's `<TextGenerateEffect>` per line, 100ms stagger).

### Page 2 — Schema discovery (`/ingest/new/postgres/discover`)

```
┌───────────────────────────────────────────────────────────────────┐
│  Ingest › New source › Postgres › Discover                       │
│  ● Intake  ● Discover  ○ Process  ○ Verify  ○ Live               │
│                                                                   │
│  Discovered 5 tables in 1.2s. Sample rows pulled.                 │
│                                                                   │
│  ┌─ SchemaTree (60%) ──────────────────┐ ┌─ Preview (40%) ─────┐ │
│  │  🔍 Filter tables ▾                  │ │ Click a table to    │ │
│  │                                      │ │ see sample rows +   │ │
│  │  ▾ schools (1,234 rows)              │ │ suggested mapping.  │ │
│  │     • id (int, pk)                   │ │                     │ │
│  │     • name (text)                    │ │ ┌─ schools ──────┐ │ │
│  │     • city (text)                    │ │ │ Sample rows:   │ │ │
│  │     • state (text, 2)               │ │ │  1  NYU  NY    │ │ │
│  │     • coda_code (text)              │ │ │  2  Harvard MA │ │ │
│  │     • updated_at (timestamp)        │ │ │  3  UCLA  CA   │ │ │
│  │                                      │ │ │  ...           │ │ │
│  │  ▾ metrics (18,130 rows)             │ │ └────────────────┘ │ │
│  │     • metric_id (uuid, pk)           │ │                     │ │
│  │     • school_id (int, fk→schools.id)│ │ Mapping suggestion: │ │
│  │     • cycle_year (text)             │ │ Node:School         │ │
│  │     • metric_name (text)            │ │ Confidence: 0.92    │ │
│  │     • metric_value (numeric)        │ │                     │ │
│  │     ...                              │ │ Why? Column 'name'  │ │
│  │                                      │ │ matches School      │ │
│  │  ▸ enrollments (8,234 rows)          │ │ alias 'name'.       │ │
│  │  ▸ audit_log (45,000 rows)           │ │ 'state' matches     │ │
│  │  ▸ admin_users (12 rows)             │ │ School.state.       │ │
│  └──────────────────────────────────────┘ └─────────────────────┘ │
│                                                                   │
│  [← Back]                          [Refresh] [Map these tables →] │
└───────────────────────────────────────────────────────────────────┘
```

**Components**: `JourneyRail`, `SchemaTree`, `Card`, animated table-discovery list (streams in from SSE).

### Page 3 — Mapping wizard (`/ingest/new/postgres/mapping`)

```
┌───────────────────────────────────────────────────────────────────┐
│  Ingest › New source › Postgres › Mapping                        │
│  ● Intake  ● Discover  ● Mapping  ○ Verify  ○ Live              │
│                                                                   │
│  Tier:   [L2 ▾]   Display name: [Partner ADEA DB]                │
│  ──────────────────────────────────────────────────────────────  │
│                                                                   │
│  Source table       Target                Confidence     Status   │
│  ──────────────────────────────────────────────────────────────  │
│  schools         →  Node: School     ▾    ███████████ 0.92  Auto │
│    Edit column mapping ▾                                          │
│  ──────────────────────────────────────────────────────────────  │
│  metrics         →  Node: Metric     ▾    █████████░░ 0.84 Review│
│    Edit column mapping ▾                                          │
│  ──────────────────────────────────────────────────────────────  │
│  enrollments     →  Edge: ENROLLED_IN ▾   ██████████░ 0.88  Auto │
│    Subject: User  Object: School                                 │
│    Edit column mapping ▾                                          │
│  ──────────────────────────────────────────────────────────────  │
│  audit_log       →  Skip              ▾   ███░░░░░░░░ 0.31 Reject│
│  ──────────────────────────────────────────────────────────────  │
│  admin_users     →  Skip              ▾   ████░░░░░░░ 0.41 Reject│
│  ──────────────────────────────────────────────────────────────  │
│                                                                   │
│  [Bulk accept Auto]  [Bulk skip Reject]  [Reset to suggestions]   │
│                                                                   │
│  ┌─ Estimated outcome ───────────────────────────────────────┐   │
│  │  Nodes: 2 types (School, Metric) — ~1,247 nodes           │   │
│  │  Edges: 1 type (ENROLLED_IN) — ~8,234 edges               │   │
│  │  Cross-graph linking: ~50 potential SAME_AS edges          │   │
│  │  Estimated pull time: ~3 min                              │   │
│  │  Estimated LLM cost: $0.00 (no LLM extraction for L2 DB)  │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                   │
│  [← Back]                      [Save as draft]  [Commit + Pull →] │
└───────────────────────────────────────────────────────────────────┘
```

**Components**: `JourneyRail`, `SchemaMappingTable` (TanStack Table with editable cells), `TierSelector`, drawer for per-column edit, `MappingCommitProgress`.

**Interactions**:
- Click "Edit column mapping" → drawer slides in from the right with a two-column layout (source columns left, target properties right) + drag-and-drop or click-to-map.
- Bulk actions confirm with a toast.
- Commit → confirmation modal recapping mapping + estimated impact + tier.
- After commit, route transitions to `/ingest/sources/{id}` with the live `ProgressStreamCard` per `04-processing-states.md`.

---

## 3. Cluster cull review (`/hitl/clusters`)

### Purpose

The user opens this after Pass 3 completes. They see ~20-200 clusters and decide which to keep, cull, merge, split, or mark anomaly. Approved clusters proceed to Pass 4 (where LLM dollars flow).

### Layout

Two-mode interface — Map mode (default, Sigma.js) and List mode (TanStack Table).

```
┌───────────────────────────────────────────────────────────────────┐
│  HITL › Cluster review                                            │
│                                                                   │
│  18 clusters pending review · Mode: [Map ▾] [List]                │
│                                                                   │
│  ┌─ Filters (left rail) ─────┐  ┌─ Cluster landscape (Sigma) ──┐ │
│  │ Corpus                    │  │                              │ │
│  │ [v1_seed         ▾]       │  │      [Cluster bubbles        │ │
│  │                           │  │       force-laid out;        │ │
│  │ Min cluster size          │  │       size = member count;   │ │
│  │ [10 ─●─────────── 500]   │  │       color = sentiment ratio│ │
│  │                           │  │       once Pass 4 has run]   │ │
│  │ Status                    │  │                              │ │
│  │ ☑ Pending                 │  │       Click a cluster to     │ │
│  │ ☐ Approved                │  │       open the detail panel │ │
│  │ ☐ Culled                  │  │       on the right.          │ │
│  │ ☐ Merged                  │  │                              │ │
│  │                           │  │       Shift-click to multi- │ │
│  │ Has Pass-4               │  │       select.                 │ │
│  │ ☐ Yes ☐ No                │  │                              │ │
│  └───────────────────────────┘  └──────────────────────────────┘ │
│                                                                   │
│  ┌─ Selected: Cluster cluster:school-selection (members: 234) ──┐│
│  │  Label: "School-selection criteria"                          ││
│  │  Description: Posts where applicants discuss which schools  ││
│  │    to apply to, based on rank, location, financial fit.     ││
│  │                                                              ││
│  │  Sample posts (top 5):                                       ││
│  │   • "Best schools for OOS applicants?" — score 24            ││
│  │   • "Tier list for dental schools?" — score 18               ││
│  │   • "Public vs private dental schools" — score 15            ││
│  │   • [more ▾]                                                 ││
│  │                                                              ││
│  │  Verdict:                                                    ││
│  │  ┌─[Keep]──[Cull]──[Merge ▾]──[Split ▾]──[Anomaly]──[Defer]┐ ││
│  │                                                              ││
│  │  Notes (optional): [                                       ]││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                   │
│  Bulk actions (5 selected):                                       │
│  [Approve all]  [Cull all]  [Merge into selected ▾]               │
│                                                                   │
│  Progress: 13 / 18 reviewed                                       │
│  [Save batch]  [Submit batch (triggers Pass 4) →]                 │
└───────────────────────────────────────────────────────────────────┘
```

### Components

- `GraphCanvas` in Level B mode.
- `Tabs` (Map / List).
- `Filter` panel.
- `ReviewCard` containing `ClusterReviewBody`.
- `VerdictPicker`.
- `BulkActionToolbar`.

### Interactions

- Single click on cluster → selection panel opens at bottom (or right, configurable).
- Shift-click adds to selection.
- `J`/`K` cycles clusters by their force-layout neighbor order.
- `A` quick-approves the current cluster (`Keep`); `R` rejects (`Cull`).
- `M` opens the merge-target picker.
- `Submit batch` confirms with a modal recapping the batch (e.g., "Cull 5, merge 2, split 1, keep 10") and the consequence ("Pass 4 will run on 10 approved clusters · est. cost $0.04").

### Edge cases

- Pass 3 hasn't run yet → empty state with "Run Pass 3 first" CTA.
- All clusters already reviewed → empty state with summary of last batch + link to Pass 4 progress.
- Mid-pass-3 (clusters appearing live) → render incrementally; banner "Pass 3 still running — additional clusters may appear."

---

## 4. Conflict review (`/hitl/conflict`)

Already partially shown in `05-trust-tier-ux.md` §7. Key add: full layout with audit trail + override + escalation.

```
┌───────────────────────────────────────────────────────────────────┐
│  HITL › Conflicts › #conflict:abc123                             │
│                                                                   │
│  ┌─ Item context ─────────────────────────────────────────────┐  │
│  │ Subject:    school:nyu_dental                              │  │
│  │ Predicate:  tuition_resident_2024-25                       │  │
│  │ Detected:   2026-05-22 14:21 UTC                           │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌── Claim A ─────────────┐    ┌── Claim B ─────────────┐        │
│  │ Value: $87,000          │    │ Value: $40,000          │        │
│  │                         │    │                         │        │
│  │ [★ L1 · preferred]     │    │ [💬 L5 · normal]        │        │
│  │ Confidence: 1.00        │    │ Confidence: 0.62        │        │
│  │                         │    │                         │        │
│  │ Source:                 │    │ Source:                 │        │
│  │ ADEA SDE2 2024-25       │    │ Reddit post abc123      │        │
│  │ Table 3, row 42         │    │ "I'm paying $40k..."   │        │
│  │                         │    │                         │        │
│  │ [View source →]         │    │ [View source →]         │        │
│  └─────────────────────────┘    └─────────────────────────┘        │
│                                                                   │
│  System resolution: L1 wins (per FR-6.1)                          │
│  Claim B will be flagged invalidated_by_official_data.            │
│                                                                   │
│  Verdict:                                                         │
│  ◉ Accept resolution                                              │
│  ○ Override — pick winner                                         │
│  ○ Temporal split (different years; both kept)                    │
│  ○ Escalate to multi-vendor judge                                 │
│                                                                   │
│  Notes (optional): [                                            ] │
│                                                                   │
│  ┌─ Audit trail ──────────────────────────────────────────────┐  │
│  │ 14:21:01  conflict_detected (resolver step 1)              │  │
│  │ 14:21:01  L1_clash_triggered (per FR-6.1)                  │  │
│  │ 14:21:01  hitl_pending (auto-escalated for human review)   │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  Progress: 1 of 2 conflicts                                       │
│  [← Previous]   [Commit + next item →]   [Defer]   [Escalate]    │
│                                                                   │
│  Keyboard: J/K next/prev · A accept · R reject · E escalate · ?  │
└───────────────────────────────────────────────────────────────────┘
```

### Components

- `ReviewCard` outer chrome.
- Two `ClaimCard` components side-by-side, each carrying `TierBadge` + `ProvenancePill`.
- `VerdictPicker` (radio group with notes).
- `AuditTrail` collapsible component.

---

## 5. Level C graph view (`/graph/analyzed`)

Already specified in `03-graph-visualization.md` §3-§14. Hero layout sketch:

```
┌────────────────────────────────────────────────────────────────────┐
│ [Sidebar]                                                          │
│ [TopBar: corpus / time / as-of / search]                          │
├────────────────────────────────────────────────────────────────────┤
│ Tabs: [Structural] [Clusters] [●Analyzed] [Crosslinks]            │
├────────────────────────────────────────────────────────────────────┤
│ ┌─ Filters (w-72) ─┐  ┌─ Canvas (flex-1) ──────┐  ┌─ Detail ────┐│
│ │ Source tier ▾    │  │                         │  │ Selected:   ││
│ │ Rank ☑ ☑ ☐       │  │                         │  │ school:nyu  ││
│ │ Status ▾         │  │  [Sigma.js WebGL        │  │             ││
│ │ Time range ▾     │  │   canvas with full      │  │ [★ L1 pref] ││
│ │ Has citation ▾   │  │   3-level styling]      │  │ TrustMeter  ││
│ │ Include anomalies│  │                         │  │ ...         ││
│ │  ☐               │  │  [Mini-map: top-right]  │  │             ││
│ └──────────────────┘  └─────────────────────────┘  └─────────────┘│
│                                                                    │
│  Citation drawer (bottom-up, toggle):                              │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ References for school:nyu_dental                             │ │
│  │  • ADEA SDE2 2024-25 — Table 3, row 42 [open]               │ │
│  │  • Partner DB — schools id=2847 [open]                       │ │
│  │  • r/DentalSchool — post abc123 [open]                       │ │
│  └──────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
```

---

## 6. PM dashboard (`/teams/pm`)

### Purpose

A product manager opens this to find what's frustrating users — pain points ranked by volume, sentiment, and tier mix. Drill into a pain point to see source citations and feature angles.

### Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  Teams › PM                                                         │
│                                                                     │
│  Filters: [Audience: All ▾] [Time: Last 90d ▾] [Min vol: 10 ▾]    │
│                                                                     │
│  ┌─ KPI strip ──────────────────────────────────────────────────┐ │
│  │  ▣ 12 pain points    ▲ 3 since last week                      │ │
│  │  ▣ 248 total mentions ▼ 12 since last week                    │ │
│  │  ▣ -0.61 avg sentiment ▼ 0.04 since last week                 │ │
│  │  ▣ 76% from L5 ▲ 5% since last week                          │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌─ Pain points (sorted by volume × |sentiment|) ────────────────┐ │
│  │                                                                │ │
│  │  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓ │ │
│  │  ┃ #1  Tuition affordability anxiety               [Open →] ┃ │ │
│  │  ┃     Volume: 248  ·  Sentiment: -0.71            ↑+12     ┃ │ │
│  │  ┃     Tier mix: ▓▓▓▓▓▓▓▓▓▓▓▓░░░░░  L5(76%) L1(20%) L2(4%) ┃ │ │
│  │  ┃     Trend last 30d:  ▁▂▃▅▇▆▅▆▆▇▇                        ┃ │ │
│  │  ┃     Top clusters: school-selection, financial-aid        ┃ │ │
│  │  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛ │ │
│  │                                                                │ │
│  │  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓ │ │
│  │  ┃ #2  DAT prep overwhelm                          [Open →] ┃ │ │
│  │  ┃     Volume: 187  ·  Sentiment: -0.58            ↑+4      ┃ │ │
│  │  ┃     Tier mix: ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░  L5(89%) L1(11%)        ┃ │ │
│  │  ┃     Trend: ▂▃▄▅▆▇▇▆▆▅▄                                   ┃ │ │
│  │  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛ │ │
│  │  ... 10 more rows                                              │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌─ Suggested action ───────────────────────────────────────────┐  │
│  │  ⚡ Pain point #1 has high volume but no L1/L2 sources cover  │  │
│  │     "what financial aid is realistically achievable." Consider│  │
│  │     adding the financial-aid section of the ADEA SDE4 report. │  │
│  │     [Connect SDE4 PDF →]                                      │  │
│  └────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### Pain-point detail (`/teams/pm/{id}`)

Click a pain point row → drill-down page:

```
┌─────────────────────────────────────────────────────────────────────┐
│  Teams › PM › Tuition affordability anxiety                         │
│                                                                     │
│  Pain point:  Tuition affordability anxiety                         │
│  Volume:      248                                                   │
│  Sentiment:   -0.71 (strong negative)                               │
│  Tier mix:    L5 76% · L1 20% · L2 4%                              │
│  Trend:       [Tremor LineChart — daily volume + sentiment]         │
│                                                                     │
│  Top contributing clusters:                                         │
│   • school-selection (108 posts)                                   │
│   • financial-aid (76 posts)                                       │
│   • cost-comparison (52 posts)                                     │
│   • loans-anxiety (12 posts)                                       │
│                                                                     │
│  Representative posts (top 5 by volume × negativity):              │
│   • "Tuition feels insurmountable" — Reddit, -0.85, 24 upvotes    │
│   • "How is everyone affording this?" — Reddit, -0.75, 18 upvotes │
│   • "Considering dropping out due to cost" — SDN, -0.92, 0 upvotes │
│   • [more ▾]                                                       │
│                                                                     │
│  Suggested feature angles (LLM-generated · Draft):                  │
│   • Cost projector tool that integrates ADEA tuition + estimated   │
│     COL + financial aid                                            │
│   • Per-school affordability rank                                  │
│   • Peer-comparison: what's typical aid package?                   │
│   [Open in Level C with these entities centered →]                 │
└─────────────────────────────────────────────────────────────────────┘
```

### Components

- `KpiCard` row (Tremor).
- `PainPointTable` (custom, TanStack Table).
- `MiniSparkline` (Tremor `SparkArea`).
- `TierMixBar` (visx stacked bar).
- `SuggestedActionCard`.
- `PainPointDetailCard` for the drill-down.
- `SuggestedAnglesPanel` with "Draft" watermark.

### Interactions

- Filter changes update the table instantly.
- Click row → detail page; back button preserves state.
- "Open in Level C" → graph view scoped to the pain point's anchor entities.
- Hover trend sparkline → tooltip with exact daily values.
- "Connect SDE4 PDF" suggested-action → opens ingestion wizard with SDE4 pre-selected.

---

## 7. Cross-cutting page rules

Apply to every hero page above:

1. **Sticky breadcrumbs** at top so users always know where they are.
2. **JourneyRail** where applicable (ingest wizard, HITL flows).
3. **Right-rail detail panel** is the consistent pattern for selection.
4. **Bottom citation drawer** is the consistent pattern for provenance drill-down.
5. **Keyboard shortcuts** always documented in a `?` overlay (Cmd-K opens command palette; J/K for list nav; A/R/E/D for verdicts on review pages).
6. **Empty / loading / error states** per `01-design-system.md` §11.
7. **Audit trail** is one click away from every detail page.

## 8. Out of V1.5 redesign scope

- Mobile responsive design for these flows. V1.5 stays desktop.
- White-label theming per tenant. V2.
- Print-friendly layouts. Out of scope.
- Real-time collaborative editing. V2.
- Onboarding tour / coach marks for first-time users. V1.6 candidate.
