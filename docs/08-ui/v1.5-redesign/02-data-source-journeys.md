# Data-Source Journey Playbook

> Per-source end-to-end UX. For each data type, this doc covers: intake → schema/preview → processing & estimates → intermediate results → graph emergence → trust-tier surfacing → user overrides → done state. Six journeys: SQL DB, Graph DB, Reddit JSONL, SDN JSONL, File upload (Excel/PDF/CSV), Website (V1.6 placeholder).

## 0. Unified journey template

Every data source follows the same five-stage UI lifecycle:

```
   ┌──────────┐    ┌──────────┐    ┌──────────────┐    ┌──────────┐    ┌──────────┐
   │ INTAKE   │ ─► │ DISCOVER │ ─► │  PROCESS     │ ─► │ VERIFY   │ ─► │ LIVE     │
   │ (Wizard) │    │ (Preview)│    │  (Streaming) │    │ (HITL)   │    │ (Dashbd) │
   └──────────┘    └──────────┘    └──────────────┘    └──────────┘    └──────────┘
   User configures Schema +        Pass 1..N runs;    User reviews    Connector
   connection +    sample rows     ETA + live counts; cross-graph     dashboard;
   tier            + auto-mapping   intermediate       links, cluster  pull on
   declaration     suggestions     viz at each pass   cull, etc.      cadence
```

Each stage has a dedicated route + page chrome treatment. Each stage has the same scaffolding: progress rail, primary action, secondary action, audit trail strip.

### Progress rail (top of every stage page)

```
   Stage 1     Stage 2     Stage 3     Stage 4     Stage 5
   INTAKE  ──► DISCOVER ──► PROCESS ──► VERIFY  ──► LIVE
   [done]     [done]      [active]    [pending]   [pending]
```

Implemented as `<JourneyRail steps={5} current={3} />`. Per ADR-012 the steps map to V1's existing state machine:
- INTAKE = `unregistered → registered` (DataSource lifecycle)
- DISCOVER = `discovered → suggested`
- PROCESS = `mapped → pulling → active` (this is where Pass 1..5 run)
- VERIFY = HITL queue items resolved
- LIVE = steady-state connector dashboard

### Time estimates — how we compute them

Every long-running operation displays an ETA. Three sources of estimate:

1. **Per-engine heuristic** — pre-warm estimate based on row count from `discover_schema` + a per-engine constant (Postgres: ~3K rows/s; SQLite: ~10K rows/s; Reddit JSONL: ~5K posts/s).
2. **Running average** — once 10% of the work is done, switch to actual rate.
3. **Phase composition** — total ETA = sum of remaining phase ETAs (Pass 1 + Pass 2 + Pass 3 + Pass 4 + Pass 5). Each phase is shown separately in the progress strip.

ETA display rules:
- `< 30s` — show "<30s" (no progress bar; just a small spinner).
- `30s–5min` — show "~3 min" with progress bar.
- `5min–1h` — show "~12 min remaining" with progress bar + completed count.
- `> 1h` — show full ETA + "you can close this tab, we'll email you when it's done" (V1.6 feature: progress polled in the background).

ETA accuracy SLA: ±20% on completed phases.

---

## 1. SQL Database (Postgres / MySQL / SQLite)

### Stage 1 — INTAKE

**Route**: `/ingest/new/{postgres|mysql|sqlite}`
**Layout**: 3-step form on the left, live "what we'll do" preview on the right.

**Form fields** (per engine):
- Connection: Host, port, database, user, password (with `CredentialField` plaintext banner per V1.5 secrets policy).
- For SQLite: file picker pointed at workstation.
- Display name (default = engine + database name).
- Tier selector (default L2; L1 requires confirmation modal per ADR-014).
- "Test connection" button → live health check.

**Right panel ("what this connector will do")**:
- Animated 4-step preview:
  1. "We'll list your tables and sample 100 rows per table."
  2. "We'll suggest how each table maps to a Node or Edge in your graph."
  3. "You'll approve the mapping (auto-approve high-confidence; review low-confidence)."
  4. "We'll pull deltas on the schedule you choose (default daily)."
- Estimated time: "~2 minutes for a typical 50-table database."

**Animation**: cards fade in sequentially (100ms stagger). Reduced-motion: appear all at once.

**Error states**:
- Connection refused → inline red ring on Host field + structured error envelope with "Common fix: check that port 5432 is reachable from this machine."
- Auth failed → inline red on Password field + "Check the credential in your `.env` file."
- SSL required → toast prompting to set `ssl_mode='require'` in the connection.

**Primary CTA**: "Connect and continue" (indigo button, `Button-lg`).
**Secondary CTA**: "Save as draft" (outline button).

### Stage 2 — DISCOVER

**Route**: `/ingest/new/{engine}/discover?source_id=...`
**Layout**: Full-width SchemaTree on the left (60%); preview + mapping suggester on the right (40%).

**SchemaTree** (left):
- Each table is a collapsible row showing: table name, column count, row count estimate, primary key, FK list.
- Click → expand to show columns with type + nullable + sample values (first 5 distinct).
- Search filter at top: filter tables by name + filter columns by name.

**MappingSuggester preview** (right):
- For each table, a `MappingProposal` card:
  - Suggested target: `Node:School` (with target's existing schema in popover).
  - Confidence: progress bar with routing chip (Auto / Review / Reject).
  - Reasoning chain: collapsible "Why we suggested this" expand.

**Streaming behavior**:
- Discovery runs in the background via Server-Sent Events to the backend.
- Each table appears in the tree as it's discovered (no "loading 200 tables" blank state).
- Suggestions appear on the right as they're computed.

**Time estimate**: typically 5-30s for a 200-table DB.

**Primary CTA**: "Map these tables" → Stage 3.
**Secondary CTA**: "Refresh discovery" (if user changed the connection).

### Stage 3 — PROCESS (Mapping + Pull)

**Route**: `/ingest/new/{engine}/mapping?source_id=...` → after commit → `/ingest/sources/{id}` with active pull state.

**Mapping wizard** (the high-effort screen):

```
┌─────────────────────────────────────────────────────────────────────────┐
│  TierSelector [L2 ▾]  Display: [Partner ADEA DB]                       │
│  ──────────────────────────────────────────────────────────────────── │
│  Source table       │  →  │  Target type      │  Confidence  │ Status │
│  ──────────────────────────────────────────────────────────────────── │
│  schools            │  →  │ Node: School ▾    │ ████████ 0.92│ Auto   │
│  metrics            │  →  │ Node: Metric ▾    │ ██████░░ 0.84│ Review │
│  enrollments        │  →  │ Edge: ENROLLED_IN │ ███████░ 0.88│ Auto   │
│  audit_log          │  →  │ Skip ▾            │ ███░░░░░ 0.31│ Reject │
│  ──────────────────────────────────────────────────────────────────── │
│  [Bulk accept Auto]  [Bulk skip Reject]  [Reset to suggestions]        │
│  ──────────────────────────────────────────────────────────────────── │
│                                                            [Commit] →  │
└─────────────────────────────────────────────────────────────────────────┘
```

- Click any row → side drawer opens with per-column property mapping editor (React Flow drag-and-drop, or a simpler two-column table for V1.5).
- Tier change → live confirmation modal if upgrading to L1.

**Commit + Pull**:

After "Commit", route transitions to `/ingest/sources/{id}` showing the live pull. ProgressStreamCard:

```
┌─────────────────────────────────────────────────┐
│ Partner ADEA DB                       [Pause]   │
│ ─────────────────────────────────────────────── │
│ Phase: Pulling rows (Pass 1)                    │
│ ███████████████░░░░░░░░░░░░  62%  ~3 min left   │
│                                                 │
│ ✓ Discovered 5 tables                           │
│ ✓ Committed mapping (4 nodes, 1 edge type)      │
│ ◐ Pulling rows: 6,234 / 10,000                  │
│ ○ Cross-graph linking                           │
│ ○ Indexing for retrieval                        │
│                                                 │
│ Last entity: school:nyu_dental                  │
│ Cost so far: $0.000  (no LLM calls for L1/L2)   │
└─────────────────────────────────────────────────┘
```

- Streaming updates via SSE.
- Cost ticker (relevant when Pass 4 LLM extraction runs — for SQL DBs it stays $0 because we don't LLM-extract from structured DBs).
- Last-entity feed shows recent materializations.

### Stage 4 — VERIFY (HITL)

After pull completes, cross-graph linking surfaces candidates. The connector dashboard shows a badge:

`5 cross-graph links pending review →`

Click → `/hitl/crosslinks?source={id}` (covered in `06-hero-page-designs.md`).

### Stage 5 — LIVE

**Route**: `/ingest/sources/{id}`
**Layout**: Connector dashboard with health card + recent pulls table + cross-link counts.

```
┌──────────────────────────────────────────────────────────────┐
│ ✓ Partner ADEA DB         L2 ▾   Daily pull at 03:00 ▾       │
│ ────────────────────────────────────────────────────────────│
│                                                              │
│  KPI cards row:                                              │
│  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐         │
│  │ Last │  │ Rows │  │ Nodes│  │ Edges│  │ Cross│         │
│  │ pull │  │ pulld│  │ mater│  │ mater│  │ links│         │
│  │ 12m  │  │ 10K  │  │ 1.2K │  │ 3.4K │  │  53  │         │
│  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘         │
│                                                              │
│  Recent pulls (TanStack Table):                              │
│  Time      Mode    Rows  Nodes  Edges  X-Links  Status      │
│  12 min    delta   10    5      8      0        ✓ ok         │
│  1d        delta   23    12     19     3        ✓ ok         │
│  2d        full    10K   1.2K   3.4K   50       ✓ ok         │
│                                                              │
│  [Pull now]  [Edit mapping]  [Disconnect…]                   │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Graph Database (Neo4j)

Mostly identical to SQL, with engine-specific affordances:

### INTAKE differences
- Connection: URI (bolt://), database name, user, password.
- Tier defaults to L2 like SQL.

### DISCOVER differences
- Tree shows **Labels** (= node types) and **Relationship types** (= edges).
- Sample per label: 100 nodes.
- Per-label property schema introspected via `db.schema.visualization()` (or Cypher fallback).

### MAPPING differences
- Each Neo4j label can map to a SecBrain node type directly (often `Label → Node:Label` 1:1).
- Each relationship type maps to a SecBrain edge type.
- Edge direction is preserved.

### PROCESS differences
- Cypher streaming pull instead of SQL SELECT.
- Pass-4 LLM doesn't run on graph-DB-sourced data (it's already structured).

### LIVE differences
- "Last pull" tracks `max(node.modified)` if present, else sync timestamp.

---

## 3. Reddit JSONL dump

### Stage 1 — INTAKE

**Route**: `/ingest/new/upload?type=reddit`
**Layout**: Drag-and-drop zone (full screen on drag-over).

**Form**:
- Two file uploads: `r_{subreddit}_posts.jsonl` + `r_{subreddit}_comments.jsonl` (both required).
- Subreddit name (auto-extracted from filename; user can override).
- Tier: locked to L5 (forum/social) — user cannot override (banner explains).
- Date range (auto-extracted from first/last post; user can narrow).
- Display name.

**Right panel preview**: animated explanation of the 5-pass cascade with cost projection.

### Stage 2 — DISCOVER

**Route**: `/ingest/new/upload/discover?source_id=...`
**Layout**: Stats summary + sample posts.

**Stats**:
```
┌────────────────────────────────────────────────┐
│ r/DentalSchool                                 │
│ ──────────────────────────────────────────────│
│   Posts:        12,453                         │
│   Comments:     87,234                         │
│   Authors:       3,891                         │
│   Span:          2018-01 → 2024-05             │
│   Flairs:        14 unique                     │
│   Median post:   142 chars                     │
│   Top flairs:    Acceptance (1,234)            │
│                  Interview (892)               │
│                  Pre-Dent (453)                │
└────────────────────────────────────────────────┘
```

**Sample posts**: 10 random posts with full text + flair + score (so user can sanity-check the dump).

**Cost projection** (rendered as a card):
- Pass 1 (structural): $0 — runs locally.
- Pass 2 (flair labels): $0 — metadata only.
- Pass 3 (clustering): ~$0.02 — local BGE embeddings + one Gemini Flash-Lite summary per cluster.
- Pass 4 (sentiment / interview-Q / conflict candidates): ~$0.18 for 12K posts on Gemini Flash-Lite (estimated; actual computed at runtime).
- Pass 5 (indexing): $0.
- **Total estimate: ~$0.20.**

### Stage 3 — PROCESS

**Route**: `/ingest/sources/{id}` with live pass progression.

**Visual**: A vertical timeline of the 5 passes. Each pass is a card showing:
- Status (pending / running / done / skipped).
- ETA / actual time.
- Output count (e.g., "Pass 1: 12,453 Post nodes + 87,234 Comment nodes").
- A small visualization preview (Pass 3 shows the emerging cluster landscape via a mini-Sigma).

```
┌────────────────────────────────────────────────────────────┐
│  Pass 1 — Structural graph                                 │
│  ✓ Done — 12.4s                                            │
│  12,453 Posts · 87,234 Comments · 3,891 Authors · 14 Threads│
│  ────                                                      │
│  Pass 2 — Cheap labels                                     │
│  ✓ Done — 2.3s                                             │
│  14 Topic nodes from flair                                 │
│  ────                                                      │
│  Pass 3 — Semantic clustering                              │
│  ◐ Running — 42% — ~3 min left                             │
│  Embedded 5,234 / 12,453 posts. Computed 18 clusters so far│
│  [mini cluster bubble preview, real-time]                  │
│  ────                                                      │
│  Pass 4 — Selective deep extraction                        │
│  ○ Queued                                                  │
│  ────                                                      │
│  Pass 5 — Knowledge surfacing                              │
│  ○ Queued                                                  │
└────────────────────────────────────────────────────────────┘
```

The user can **cull clusters mid-flight** during Pass 3 if obviously-junk clusters emerge — `/hitl/clusters` opens in a sheet from the timeline.

### Stage 4 — VERIFY

After Pass 3 completes, sheet auto-opens with cluster cull review (or user opens manually per V1.5-R1 Q14). After Pass 4 completes, sheet auto-opens with node/edge proposal review.

### Stage 5 — LIVE

Connector dashboard with subreddit stats + recent pulls (mostly N/A for static dumps; show cluster + sentiment ratios instead).

---

## 4. SDN JSONL dump

Same shape as Reddit with two differences:

**INTAKE**:
- Two file uploads: `sdn_thread_metadata.jsonl` + per-thread `thread_*_posts.jsonl` files (multi-file upload).
- Forum category filter (so user can ingest only "Pre-Dental" or "Dental School").
- Tier locked to L5.

**DISCOVER**:
- Stats show: thread count, post count, unique authors, span, category distribution.
- No flair (SDN uses category instead).
- No upvote signal — credibility rubric uses the SDN-specific 7-feature scoring per ADR-008.

**PROCESS**:
- Same 5-pass cascade.
- Pass 2 promotes SDN `category` to Topic nodes (instead of Reddit flair).
- Cluster output similar.

---

## 5. File upload (Excel / PDF / CSV / JSONL generic)

**Route**: `/ingest/new/upload`
**Layout**: Drag-and-drop zone with file-type auto-detection.

**Detection logic**:
- `.xlsx` → routes to L1 Excel adapter (ADEA-shaped detected by sheet structure).
- `.pdf` → L1 PDF adapter (SDE4-shaped detected by content + page structure).
- `.csv` → CSV adapter (V1.5a addition? — confirm in V1.5-fix scope, not in V1.5 ship).
- `.jsonl` → Reddit/SDN auto-detection based on field shape.

**Tier**:
- L1 PDF / Excel default to L2 with L1-upgrade option (gated).
- JSONL detection enforces L5 if Reddit/SDN-shaped.

**Discovery**:
- For Excel: sheet picker + column preview per sheet.
- For PDF: page count + first-page text preview + extraction strategy ("text-PDF" vs "scanned-PDF; OCR required").
- For CSV: column header detection + sample rows.

**Mapping**: Same wizard as SQL DB, but the columns come from sheet / CSV headers instead of DB introspection.

**Processing**: Pass 1 + Pass 2 only for L1 (no extraction needed); full 5 passes for L5.

---

## 6. Website (V1.6 placeholder)

Reserved for V1.6. Out of V1.5 scope.

Expected shape:
- INTAKE: URL + crawl depth + domain allowlist + tier (default L4 raw web).
- DISCOVER: sitemap + sample pages + content-type breakdown.
- PROCESS: crawl + extract + structure + Pass 1-5.
- VERIFY + LIVE: same as other sources.

---

## 7. Slack export (V1.6 placeholder)

Reserved for V1.6. Out of V1.5 scope.

Expected shape:
- INTAKE: ZIP export from Slack admin + channel picker + DM inclusion toggle + tier (default L5).
- DISCOVER: channels + member count + thread depth.
- PROCESS: similar to Reddit but with channel + thread + reaction signal.
- Special concern: PII / privacy — anonymization defaults ON.

---

## 8. The journey-rail component spec

`<JourneyRail>` is the visual progress strip at the top of every stage. Implementation:

```tsx
<JourneyRail
  steps={[
    { id: 'intake',   label: 'Intake',   status: 'done',     href: '/ingest/new/postgres' },
    { id: 'discover', label: 'Discover', status: 'done',     href: '/ingest/new/postgres/discover' },
    { id: 'process',  label: 'Process',  status: 'active',   href: '/ingest/sources/abc' },
    { id: 'verify',   label: 'Verify',   status: 'pending',  href: '/hitl/crosslinks?source=abc' },
    { id: 'live',     label: 'Live',     status: 'pending',  href: '/ingest/sources/abc' },
  ]}
/>
```

Visual:
- Each step is a pill with icon (matches step) + label + status indicator.
- Connecting lines between pills are colored by progress (indigo if both ends complete; gradient if one is active; muted gray if pending).
- Active step pulses (subtle, respects reduced-motion).
- Clicking a completed step navigates back; clicking a pending step is disabled.

## 9. Cross-cutting UX rules

1. **Always show provenance**. Every data point that ends up in the graph carries `references` and the UI shows them on hover. `ProvenancePill` is the inline carrier.
2. **Always show cost**. Every page that triggers an LLM call shows the running cost. Audit page rolls them up.
3. **Always show what's loading**. Skeletons matching final layout, not spinners.
4. **Always allow undo**. Sonner toasts with 5s undo for HITL decisions, mapping commits, tier changes.
5. **Always preserve user state**. URL params + localStorage for filters, selections, drafts. Closing a tab mid-flow doesn't lose work.
6. **Always confirm destructive**. Cluster cull, disconnect-with-purge, mapping reset → confirmation modal naming the affected entities.
7. **Always link back to audit**. Any state change has a "View in audit log" link.

## 10. Out of V1.5 redesign scope

Reserved for V1.6:
- Website crawl ingestion UX.
- Slack export ingestion UX.
- Multi-file batch upload with per-file mapping.
- Scheduled exports (Slack DMs into your private corpus weekly).
- Per-source dashboard customization (rearrange KPI cards).
- Multi-user shared review queues (V2 multi-tenant).
- Mobile responsive on stages 2–4 (V2; V1.5 stays desktop).
