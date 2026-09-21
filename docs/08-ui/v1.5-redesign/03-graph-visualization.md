# Graph Visualization Spec

> The visual centerpiece of V1.5. Three views (Level A structural, Level B clusters, Level C analyzed) + a cross-graph anchor view. Sigma.js + WebGL. This doc covers rendering choices, layout, interaction, and the visual encoding for trust tiers, ranks, and statuses.

## 0. Why this doc exists

`docs/08-ui/graph-level-views.md` already specified what each level is. This doc specifies *how it actually looks and behaves*. The V1.5 implementation shipped a `GraphResults.tsx` table fallback — that's a fallback, not the primary surface. The primary surface is a graph canvas.

## 1. Tech stack

| Layer | Library |
|---|---|
| Canvas | Sigma.js v3 (WebGL renderer) |
| Graph model | graphology |
| Layout | graphology-layout-forceatlas2 (Web Worker) |
| Hover / interaction | Sigma's built-in event system + custom React state synced via `useSigma()` hooks |
| Animation | Framer Motion (for selection panel slide + drawer transitions) |
| Mini-map | Sigma's built-in mini-map plugin |
| Search | Custom `EntitySearch` component + Sigma's `nodes().filter()` |
| Fallback table | TanStack Table — also serves as the WCAG "view as table" accommodation |

Bundle impact: ~80 KB gzipped, lazy-loaded only on `/graph/*` routes.

## 2. Three-view contract

Per ADR-012:

| View | Route | Retrieval API | What's rendered |
|---|---|---|---|
| **Level A — Structural** | `/graph/structural` | `query_graph_structural` | Users, Posts, Comments, Threads, Subreddits + AUTHORED/REPLIED_TO/UPVOTED edges. Pure Pass-1 output. |
| **Level B — Clusters** | `/graph/clusters` | `query_graph_clusters` | Topic + Cluster nodes + IN_CLUSTER + REFERENCES_TOPIC edges + cluster summaries. Pass-2 + Pass-3 output. |
| **Level C — Analyzed** | `/graph/analyzed` | `query_graph_analyzed` | Full graph: all node types, all edges, sentiment / interview-Q / conflict claims, cross-graph SAME_AS, status flags. Pass-4 + cross-graph. |
| **Cross-graph anchors** | `/graph/crosslinks` (optional sub-view of Level C) | `query_graph_crosslinks` | SAME_AS edges only, between L1/L2/L5 entities. Side-by-side evidence panels. |

## 3. Visual encoding

### Node shapes

| Node type | Shape | Notes |
|---|---|---|
| User (Reddit/SDN) | Circle | |
| Post | Rounded square | |
| Comment | Small rounded square | half-size of Post |
| Thread | Hexagon | |
| Subreddit / SDN Category | Diamond | |
| School (canonical L1) | Star (5-point) | indicates ground-truth status |
| Program | Triangle | |
| Topic | Pill (wide rounded rect) | |
| Cluster | Large circle | Level B only |
| L2 Document | Open book glyph | |
| L1 Document (PDF) | Closed book glyph | |
| Claim | Diamond outline | |
| External DB entity | Square w/ engine icon | Postgres/MySQL/Neo4j/SQLite |

### Node colors (by tier; per `01-design-system.md` palette)

| Tier | Node fill | Node stroke |
|---|---|---|
| L1 | `--tier-l1-bg` | `--tier-l1` (1.5px) |
| L2 | `--tier-l2-bg` | `--tier-l2` (1.5px) |
| L3 | `--tier-l3-bg` | `--tier-l3` (1.5px) |
| L4 | `--tier-l4-bg` | `--tier-l4` (1.5px) |
| L5 | `--tier-l5-bg` | `--tier-l5` (1.5px) |

In dark mode, fills get a lower alpha (12%) and strokes stay at 100% — the tier color "glows" against the dark background.

### Node size (by importance)

Calculated per view:

- **Level A**:
  - User size = `8 + 1.5 × sqrt(post_count + 0.5 × comment_count)`. Min 8px, max 32px.
  - Post size = `8 + 0.8 × sqrt(score + 1)` for Reddit; `8 + sqrt(comment_count)` for SDN.
  - Thread size = `8 + sqrt(member_count)`.
- **Level B**:
  - Cluster size = `12 + 1.2 × sqrt(member_count)`. Min 16px, max 64px.
  - Topic size = fixed at 14px.
- **Level C**:
  - All structural nodes scale per Level A rules.
  - Claim nodes scale by `support_count - contradict_count` (positive = larger, negative = smaller).

### Edge styling

| Edge type | Stroke | Color |
|---|---|---|
| `AUTHORED` | Solid, 0.5px | `--foreground` at 30% opacity |
| `REPLIED_TO` | Solid arrowed, 0.5px | `--foreground` at 50% opacity |
| `UPVOTED` | Solid, 0.3px | `--info` at 30% opacity (Level A toggle) |
| `BELONGS_TO_THREAD` | Implicit (force layout); no edge drawn | |
| `IN_CLUSTER` | Solid, 0.3px | `--tier-l5` at 20% opacity |
| `REFERENCES_TOPIC` | Solid, 0.5px | `--accent` at 60% opacity |
| `MENTIONS_SCHOOL` | Solid, 1px | `--tier-l1` at 80% opacity |
| `SUPPORTS` | Solid, 1px | `--success` |
| `CONTRADICTS` | Solid, 1px | `--destructive` |
| `SAME_AS` | Solid 1.5px, dotted weak ends | `--accent` (gold) |
| `WEB_VERIFIED` | Dotted, 1px | `--info` |

**Rank modifier** applied to all edges:
- `preferred` → 1.5× stroke width.
- `normal` → 1× stroke width (default).
- `deprecated` → dashed (5px on, 3px off) + 40% opacity.

### Status overlays

Drawn as Sigma `nodeReducer` post-processing:

| Status | Visual |
|---|---|
| `invalidated_by_official_data` | Red strikethrough line across the node + thin red border |
| `anomaly` | 2px orange ring (`--warning`) around the node |
| `hitl_pending` | Pulsing yellow ring (1.5s loop; respects reduced-motion) |
| `superseded` | 50% opacity, no other change |
| `committed` | Subtle green dot at NE position |

## 4. Layout

### Default — ForceAtlas2 (Web Worker)

Run in a Web Worker so the main thread stays responsive. Parameters:

```js
{
  iterations: 200,             // initial settle
  worker: true,
  settings: {
    gravity: 1,
    scalingRatio: 12,
    strongGravityMode: false,
    barnesHutOptimize: true,    // for > 1000 nodes
    barnesHutTheta: 0.5,
    slowDown: 1,
  }
}
```

On initial load:
- Phase 1 (200ms): instant snap to last-known positions (cached in localStorage by graph hash).
- Phase 2 (1-3s): ForceAtlas2 settles. Nodes ease into final positions (Framer Motion `<motion.g>` per node).
- Phase 3 (post-settle): layout pauses; only resumes on graph change (new nodes/edges).

### Per-level layout tuning

- **Level A** (high node count): `scalingRatio: 18`, `barnesHutOptimize: true`. Nodes spread wide; communities cluster naturally.
- **Level B** (low node count, ~20-200 clusters): `scalingRatio: 30`, `gravity: 1.5`. Clusters spread to fill canvas evenly.
- **Level C** (mixed): `scalingRatio: 12`, `gravity: 1`. Tight clustering, supports drill-down.

### Alternative layouts (selectable from a layout-picker)

- **Hierarchical** (for thread structures): top-down DAG using `graphology-layout/dagre`.
- **Radial** (for "everything around one entity"): user picks a focal node; tree radiates.
- **Geographic** (V1.6): for entities with `lat/lon` (e.g., dental schools by US state).

## 5. Interaction model

### Hover

- Node hover: cursor changes to pointer; node gains a 2px ring in `--ring`; connected edges fade up to 100% opacity (others fade to 20%).
- Edge hover: same fade pattern; tooltip shows edge type + rank + confidence.
- Both: 100ms transition.

### Click (select)

- Node click: enters selection mode. Right panel slides open (Framer Motion x: 100% → 0, 200ms).
- Selected node: 2× stroke width + `--ring` color.
- Click empty canvas: clears selection.

### Multi-select

- Cmd-click adds to selection.
- Shift-drag lassoes (Sigma's built-in selection plugin).
- Selection persists across view changes (URL param `?selected=id1,id2,...`).

### Zoom + pan

- Mouse wheel zooms (centered on cursor).
- Drag pans.
- Pinch zoom on touchpad / touch.
- Keyboard: `+`/`-` zoom; arrow keys pan; `0` resets view.

### Drill-down

- Double-click a cluster (Level B) → opens that cluster on Level C with the cluster selected.
- Double-click a user (Level A) → opens that user on Level C with their authored content + claims highlighted.
- Path-find: select two nodes → click "Find path" → shows shortest path with all intermediate nodes highlighted.

### Search (top of canvas)

- `EntitySearch` component (full-text + alias-aware).
- Selecting a result centers + highlights the node.
- Recent searches in localStorage; cmd-K opens the same search globally.

## 6. Right panel (selection details)

Slides in from the right when a node is selected. Fixed width `w-96` (384px); collapsible.

**Contents (per node type)**:

### User
- Header: avatar (initials) + display name + `@username` + tier badge.
- Stats grid: post count, comment count, upvotes received, credibility score.
- `TrustMeter` widget: visual breakdown of tier × rank × credibility.
- Recent posts list (paginated).
- "View on Level C with this user centered" button.

### Post
- Header: post title + flair + score + author link.
- Body excerpt (first 200 chars, expandable).
- Cluster membership + sentiment ratio if Pass-4 has run.
- Claims extracted (list with confidence + rank).
- `CitationDrawer` toggle for full provenance.

### Cluster
- Header: cluster label (Pass-3 summary) + member count.
- Description (1-sentence + expandable).
- Sentiment ratio.
- Sample posts (top 5 by representative score).
- "Review this cluster" button → opens cluster-cull review.

### Claim
- Subject + predicate + object as a sentence.
- Confidence + rank + source tier.
- `ProvenancePill` for the source (post / DB row / URL).
- Conflict status (if applicable) with link to conflict review.
- "Web-verify this claim" button (if not already done).

### Cross-link
- Side-by-side cards: left = anchor entity (e.g., ADEA L1 school), right = source entity (e.g., Postgres connector school).
- Similarity score + confidence.
- "Accept this link" / "Reject" / "Defer" CTAs if pending HITL.

## 7. Citation drawer

Bottom drawer (Vaul). Always togglable from the bottom-right of every graph view.

When open + node selected: shows full `references` list for that node, clickable to:
- Source post (opens external link in new tab).
- Source DB row (opens connector detail page).
- Source URL (opens external — with `noopener noreferrer`).
- Audit log entry (opens audit detail).

Per accessibility: keyboard accessible (Esc to close; Tab to cycle links).

## 8. Mini-map

Top-right of canvas. 200×120px Sigma mini-map showing the entire graph with current viewport highlighted.

- Click-drag on mini-map → pans main canvas.
- Auto-collapses on `< xl` screens.
- Always visible on Level C; optional toggle on Levels A + B.

## 9. Filter rail (left)

Collapsible left rail. Width `w-72` (288px).

**Per view**:

### Level A
- Source type (Reddit subreddits, SDN categories, ADEA, external DB).
- Date range.
- Min author credibility.
- Has school mention (toggle).
- Has Pass-4 extraction (toggle, V1.5c+).

### Level B
- Corpus.
- Date range.
- Min cluster size.
- Review status (pending / approved / culled / etc.).

### Level C
- Source tier range (slider L1–L5).
- Rank (preferred / normal / deprecated multi-select).
- Status flags (include_anomalies, hitl_pending, etc.).
- Time range + as-of date.
- Has-citation min N.

All filters mirror to URL params + write to `audit_log` with `kind=ui_filter_change`.

## 10. Performance budget

| Metric | Budget | Mitigation |
|---|---|---|
| Initial render (5K nodes) | < 2s | localStorage layout cache; Web Worker for FA2 |
| Initial render (50K nodes) | < 4s | viewport culling (only render in-viewport nodes); LOD (low detail on far-out zoom) |
| Hover-to-tooltip | < 50ms | preloaded `node.attributes` |
| Click-to-selection | < 100ms | optimistic UI update + background data fetch |
| Pan / zoom | 60 fps | WebGL renderer; no DOM nodes for graph |

Sigma's `nodeReducer` runs on every render — keep it cheap. Status overlays computed once and cached.

## 11. Accessibility

Per `docs/08-ui/accessibility.md` + this redesign's `09-accessibility.md`:

- Canvas is wrapped in `<div role="application" aria-label="Graph viewer">` + off-screen `aria-live="polite"` region announcing selection ("School: New York University College of Dentistry selected").
- "View as table" button always visible (top-right of canvas).
- Keyboard navigation:
  - Tab cycles selectable nodes in force-layout order.
  - Enter activates selection.
  - Esc clears.
  - Arrow keys pan.
  - `+` / `-` zoom.
- Color is never the only signal — every tier has a shape + icon glyph component in addition to color.
- Reduced-motion: FA2 layout snaps to final positions without animation; selection panel slide is instant.

## 12. Empty + loading + error states

### Empty (no data for the current query/filter)

```
┌──────────────────────────────────────────────┐
│                                              │
│            [graph icon, large]               │
│                                              │
│        No nodes match your filters           │
│                                              │
│   Try widening the time range or removing    │
│         the source-tier filter.              │
│                                              │
│   [Reset filters]    [Open in Level C]       │
│                                              │
└──────────────────────────────────────────────┘
```

### Loading

Skeleton: canvas placeholder with shimmer + filter rail skeleton + right panel skeleton. Not a full-page spinner.

### Error

```
┌──────────────────────────────────────────────┐
│  ⚠  Graph store didn't respond               │
│                                              │
│  Check the audit log for details, or         │
│  retry the query.                            │
│                                              │
│  [Retry]    [View audit log]                 │
│                                              │
│  ┌──────────────────────────────────────┐    │
│  │ Technical details (collapsible)      │    │
│  │ HTTP 503 from KuzuGraphClient...     │    │
│  └──────────────────────────────────────┘    │
└──────────────────────────────────────────────┘
```

## 13. Cross-graph anchor view (`/graph/crosslinks`)

Sub-view of Level C dedicated to SAME_AS edges. Layout:

```
┌─────────────────────────────────────────────────────────────────────┐
│  Source A: ADEA L1                       Source B: Partner Postgres │
│  ───────────────────────────             ─────────────────────────  │
│                                                                     │
│  [Star]──────  SAME_AS  ───────[Square]                             │
│   NYU                            school:partner_2847                │
│   College of Dentistry           "NYU Dental Med"                   │
│                                                                     │
│  Tier: L1            conf: 0.94          Tier: L2                   │
│  rank: preferred                                                    │
│                                                                     │
│  Side-by-side evidence:                                             │
│  ┌──────────────────────┐  ┌──────────────────────┐                │
│  │ ADEA SDE2 2024-25    │  │ Partner row id=2847  │                │
│  │ tuition: $87,000     │  │ tuition: $87,000     │                │
│  │ ...                  │  │ ...                  │                │
│  └──────────────────────┘  └──────────────────────┘                │
│                                                                     │
│  Pending HITL items: 5 →                                            │
└─────────────────────────────────────────────────────────────────────┘
```

Each cross-link is rendered as a row. Filter by tier pair (L1↔L2, L1↔L5, etc.). Sort by confidence.

## 14. URL state contract

Every interaction reflects to URL params so views are shareable / bookmarkable:

```
/graph/structural
  ?corpus=v1_seed
  &q=NYU
  &time_range=2023-01-01,2024-12-31
  &as_of=2024-12-31
  &filter.tier_min=L4
  &filter.has_mention=true
  &selected=user:reddit:DentalSchool:alice
  &layout=force
  &show_mini_map=true
```

Sharing the URL re-creates the exact state on another machine.

## 15. Out of V1.5 scope

- 3D graph rendering (V1.6 candidate via Reagraph).
- Direct in-canvas editing (merge nodes, split clusters). Edits go through HITL surfaces.
- Real-time collaborative selection (V2 multi-tenant).
- Per-user saved views / layouts (V1.6).
- Geographic layout for entities with lat/lon (V1.6).
