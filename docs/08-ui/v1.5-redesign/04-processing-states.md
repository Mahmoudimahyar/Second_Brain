# Processing States — Unprocessed, Processing, Intermediate, Done

> How we show the user where their data is in the pipeline. The single biggest UX gap in the V1.5 implementation was loading-state opacity — the user never knew if anything was happening. This doc fixes that.

## 0. The state vocabulary

Every entity in the system is in one of these states at any moment:

| State | Meaning | Visual signal |
|---|---|---|
| **Unprocessed** | Raw, ingested but no extraction or analysis yet | Muted color (zinc), no border emphasis, "queued" badge |
| **Queued** | Scheduled for a pass | Yellow pulse, "queued for Pass N" tooltip |
| **Processing** | Currently in a pass | Animated indigo border, ETA badge, live counter |
| **Intermediate** | Some passes done; more queued | Partial tier color + count of completed passes |
| **HITL-pending** | Awaiting human review | Yellow pulse + review queue chip |
| **Done — committed** | Fully processed + reviewed | Full tier color + green checkmark |
| **Anomaly** | Done but flagged as outlier | Orange ring + tooltip explaining why |
| **Invalidated** | Done but contradicted by L1 | Red strikethrough |
| **Superseded** | Replaced by newer ingest | 60% opacity + clock icon |

These states map to the `status` field in V1's data model and the `state_transition` audit-log kind.

## 1. Page-level processing UI

When a connector is mid-pull or Pass-4 is running, the page chrome shows a persistent processing card:

```
┌───────────────────────────────────────────────────────────────┐
│  ◐ Pulling r/DentalSchool                                     │
│  Pass 4 — Selective deep extraction                           │
│  ──────────────────────────────────────────────────────────  │
│  ███████████████░░░░░░░░░  62%   ~3 min 12s left              │
│                                                               │
│  Processed:    7,732 / 12,453 posts                           │
│  Cost so far:  $0.11    (budget: $0.50)                       │
│  Cache hits:   84%                                            │
│                                                               │
│  ✓ Pass 1 — Structural        12.4s                           │
│  ✓ Pass 2 — Cheap labels       2.3s                           │
│  ✓ Pass 3 — Semantic clusters  3 min 18s                      │
│  ◐ Pass 4 — Deep extraction    62% — 3 min 12s left           │
│  ○ Pass 5 — Indexing           queued                         │
│                                                               │
│  [View detail] [Pause] [Cancel]                               │
└───────────────────────────────────────────────────────────────┘
```

**Live updates**: via Server-Sent Events from `/api/v1/sources/{id}/pulls/{pull_id}/stream`. Backend emits JSON events every 1-2s.

**ETA computation**: described in `02-data-source-journeys.md` §0. The progress bar uses the running-average rate; the per-phase ETA decomposes by remaining phases.

**Tab + browser handling**:
- The processing card persists in the layout (top of `<main>`) until cancelled or complete.
- If the user navigates away, it shrinks into a sidebar badge (e.g., "1 pull in progress" on the sidebar nav item).
- If the user closes the tab, processing continues server-side. On return, the card re-appears with current state.

## 2. Intermediate result previews

The user shouldn't have to wait for a 30-minute Pass 4 to know what's happening. We expose intermediate results at three checkpoints:

### Checkpoint A — After Pass 1 (structural)

Right column of the pull page shows:
- **Graph snapshot**: a small Sigma.js canvas (200×200px) rendering the just-created structural subgraph at low detail. Updates every 5s as more nodes materialize.
- **Stats**: node count by type (Users, Posts, Comments) — live counter.
- **Quick query**: "Who's the most active author in this dump so far?" type queries (canned, instantaneous on the partial graph).

### Checkpoint B — After Pass 3 (clustering)

- **Cluster landscape**: full-screen `Level B` graph view, even though Pass 4 isn't done yet.
- **Cluster cards**: top 20 clusters by size, with summaries and sample posts.
- **CTA**: "Review clusters before Pass 4 runs?" — opens cluster-cull review in a sheet.
- **Skip option**: "Run Pass 4 on all clusters" (auto-approve).

This is the user's natural intervention point for cost control — kill bad clusters before LLM dollars flow.

### Checkpoint C — Mid Pass-4 (live extraction)

- **Sample extractions**: a streaming feed showing the last 10 Pass-4 outputs — sentiment, interview-Q, conflict candidate — with full provenance.
- **Confidence histogram**: live-updating bar chart of confidence distribution. Tells the user "most extractions are confident" vs "lots of low-confidence" early.
- **Cost ticker**: $0.07 / $0.50 budget — running spend updates per call.
- **Pause-on-budget alert**: at 80% of budget, modal: "Approaching budget cap. Continue, pause, or raise the cap?"

## 3. List-level state indicators

Anywhere we show a list of entities (HITL queue, audit log, source dashboard recent pulls), each row carries its state:

```
[●  state-color  ] [icon] [title]  ... [meta] [...]
```

Where the state-color is:
- Muted gray dot = unprocessed
- Yellow pulse = HITL-pending / queued
- Indigo spinner = processing
- Green check = done
- Orange ring = anomaly
- Red strike = invalidated

This is consistent across every list view.

## 4. Per-entity state surface (selection panel)

When a node is selected in the graph or a row is clicked in a list, the right panel shows a state strip at the top:

```
┌─────────────────────────────────────────────┐
│  ✓ school:nyu_dental                        │
│  Done · L1 · rank=preferred · 53 mentions   │
│                                             │
│  Lifecycle:                                 │
│  ✓ Pass 1 — structural (2024-05-22 14:21)   │
│  ✓ Pass 2 — labels      (2024-05-22 14:23)  │
│  ✓ Pass 3 — clusters    (2024-05-22 14:45)  │
│  ✓ Pass 4 — extractions (2024-05-22 15:08)  │
│  ✓ Pass 5 — indexed     (2024-05-22 15:09)  │
│  ✓ Cross-graph linked   (2024-05-22 15:12)  │
│    — 3 SAME_AS edges to external sources    │
│  ─────────                                  │
│  Audit trail (12 events)  [expand]          │
└─────────────────────────────────────────────┘
```

Lifecycle is a vertical timeline. Each row is a state transition. Clicking expands to show the audit-log entry inline.

## 5. The audit page as state archaeology

`/audit` is not just compliance. It's the user's tool for understanding **why** something is in a given state.

Layout:

```
┌──────────────────────────────────────────────────────────────────┐
│  Filters: [time] [kind] [actor] [corpus] [source] [entity]       │
│  ────────────────────────────────────────────────────────────── │
│  Live (last 5 min):                                              │
│    14:23:01  ✓ committed  HITL alias_match  alice→user:reddit:... │
│    14:22:47  ◐ running    Pass 4 sentiment  post:abc123          │
│    14:22:33  ✓ done       Pass 3 cluster    "school-selection"   │
│  ────────────────────────────────────────────────────────────── │
│  History:                                                        │
│  [TanStack Table with full pagination]                           │
│                                                                  │
│  Cost summary (last 24h):  $1.24                                 │
│  By task:    sentiment $0.31 · interview-Q $0.43 · cluster $0.50 │
│  By vendor:  Gemini $0.78 · Haiku $0.46                          │
└──────────────────────────────────────────────────────────────────┘
```

## 6. Notification surface

Long-running operations (> 5 min) trigger:
- A toast at the moment of trigger ("Pass 4 on r/DentalSchool started — ETA 12 min").
- A persistent sidebar badge ("Pass 4 running") with click-to-detail.
- On completion: a toast ("Pass 4 finished — 12 cluster summaries, 1,247 sentiments, $0.18 spent") with "View" CTA.
- On failure: an error toast with "View error log" CTA.

V1.6: optional email / Slack notification for jobs > 30 min.

## 7. Error states inline

When a pass fails mid-flight:
- The phase card flips to red with an error icon.
- Cost ticker freezes at last-known.
- "Retry from this phase" button + "View error details" expand.
- Audit log entry written with full traceback.

For partial failures (e.g., 9,000 of 10,000 posts processed, 1,000 errored):
- Show a partial-success card: "8,732 processed successfully · 268 failed".
- "Retry failed only" button.
- Per-row error inspection via drill-down.

## 8. Pause / cancel / resume semantics

| Action | Effect |
|---|---|
| **Pause** | Phase finishes its current batch; further work suspended. Connector state → `paused`. Can resume later. |
| **Cancel** | Phase aborts. Materialized nodes from completed passes preserved (with `t_ingest_to` set). User confirms. |
| **Resume** | Continues from last cursor. Picks up where it left off. |

Pause is the default user override; Cancel requires confirmation.

## 9. Component spec: `ProgressStreamCard`

The reusable card that shows pass-by-pass progress. Props:

```tsx
interface ProgressStreamCardProps {
  pullId: string;
  sourceId: string;
  sourceName: string;
  phases: PhaseStatus[];
  currentPhase: string | null;
  eta: number | null;     // seconds remaining
  costUsd: number;
  costBudget: number;
  cacheHitRate: number | null;
  lastEntityId: string | null;
  onPause: () => void;
  onCancel: () => void;
  onViewDetail: () => void;
}
```

Subscribes via TanStack Query + SSE to `/api/v1/sources/{sourceId}/pulls/{pullId}/stream`.

## 10. Sample-result feed component

`<SampleResultFeed>` — a live-updating list of the last 10 outputs from a running pass. Used inside the processing card during Pass 4.

```tsx
interface SampleResultFeedProps {
  pullId: string;
  passId: 'pass1' | 'pass2' | 'pass3' | 'pass4' | 'pass5';
  maxItems?: number;        // default 10
  showConfidence?: boolean;
  onItemClick?: (item: ExtractionItem) => void;
}
```

Renders each item with:
- Type icon (sentiment / Q / claim).
- Excerpt (max 100 chars).
- Confidence chip.
- Source link.
- Timestamp (relative: "3s ago").

New items slide in from the top with a 200ms fade + slight translate-y (per `08-motion-language.md`).

## 11. Tabs + view persistence

When the user closes the tab mid-process:
- State persists server-side (Prefect tracks it).
- Returning: card automatically resumes its live state.
- If process completed in absentia: card shows "Completed at 14:23. View summary?" CTA.

When the user has many tabs open (multiple pulls running):
- Sidebar shows aggregate badge "3 pulls in progress".
- Click → drops to `/ingest` with pull-progress for all live sources.

## 12. Cost ceiling enforcement

Per ADR-016 v2 + V1.5c cost cap:
- Each corpus has a budget.
- Real-time spend tracked.
- At 80% → toast warning "Approaching budget" (yellow). Continue.
- At 100% → modal "Budget reached. Choose: pause, increase budget, or cancel." No further LLM calls until user resolves.

Audit-logged via `web_search_cap_warning` + `web_search_cap_hit` kinds.

## 13. Edge cases

- **Empty dump**: "We pulled 0 rows. Check your filter or date range."
- **Schema drift since last pull**: red banner on connector dashboard explaining what changed; user can re-discover.
- **Tier downgrade attempted**: if user changes a connector from L1 to L2, modal: "This will close `t_ingest_to` on N L1 edges and re-open them as L2. Continue?"
- **Concurrent pull on same source**: refused with structured error; UI shows "Already pulling — wait or cancel the current pull."
- **Cache invalidation cascade**: changing the feedback-loop policy invalidates Pass-4 cache for affected templates. Toast: "Cache invalidated for `extract_sentiment` (148 entries). Next Pass 4 will re-extract." with "View affected entries" link.

## 14. Implementation notes

- Server-Sent Events (SSE) is the streaming primitive (not WebSocket — simpler, fine for one-way streams).
- `EventSource` API in the browser.
- Heartbeat every 30s; reconnect on disconnect.
- Backend implementation: FastAPI's `StreamingResponse` + Prefect's flow-run events.

Backend route shape:

```
GET /api/v1/sources/{source_id}/pulls/{pull_id}/stream

EventSource events:
- "phase_started": {phase, ts}
- "phase_progress": {phase, processed, total, eta_seconds, cost_usd_so_far, cache_hit_rate}
- "phase_completed": {phase, duration_seconds, output_summary}
- "sample_extraction": {pass_id, item}   // throttled to 1/s max
- "cost_warning": {threshold, current, budget}
- "error": {phase, message, recoverable}
- "completed": {summary}
```
