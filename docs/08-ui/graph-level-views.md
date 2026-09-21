# Multi-level Graph Views — Render Contract

> Render contract for the three graph-view pages in V1.5b. Each view is independent (separate route, separate API call, separate Pydantic+Zod schema). See ADR-012 for the underlying retrieval contract; this doc covers what the user sees.

## Why three views

The user described three mental models of the graph:

1. **Level A — deterministic structural** — "who said what, where, when, with how many upvotes." Pure forum mechanics. No interpretation.
2. **Level B — similarity-grouped** — "what are the natural clusters of posts." Topic landscape. Used to decide what to deep-extract next.
3. **Level C — fully analyzed** — "what entities, claims, and conflicts the system has resolved from this data." The decision-grade graph.

Conflating them into one viewer hides what each is for. ADR-012 splits the retrieval contract; this doc splits the UI.

## Common chrome (every view)

All three views share:

- Top bar with corpus + time-range + as-of pickers. Defaults to current corpus + last 12 months + now.
- Right-side panel that swaps content based on selection: empty state, single-node detail, multi-select metrics.
- Bottom-left zoom controls (`+`, `-`, fit-to-view, reset).
- Bottom-right citation drawer toggle — when a node/edge is selected, the drawer expands with full `references` list, clickable to the source row/post.
- Top-right view-switcher chips: `Structural` | `Clusters` | `Analyzed`. Cmd/Ctrl+1/2/3 keyboard shortcut.

Every view uses Sigma.js as the canvas, WebGL renderer, force-directed layout by default (ForceAtlas2 with sigma-iv2).

## Level A — `/graph/structural`

**Source API**: `GET /api/v1/graph/structural?query=...&time_range=...&as_of=...&traversal_depth=2`

**Render rules:**
- Node shapes: User = circle; Post = square; Comment = small square; Thread = hex; Subreddit = diamond.
- Node sizes: User → linear in `(post_count + 0.25 × comment_count)`; Post → linear in `score` (Reddit) or comment count (SDN); Thread → linear in member count.
- Node colors by source: Reddit subreddits = blue palette; SDN categories = purple palette; ADEA = gold.
- Edges: AUTHORED (solid black, thin), REPLIED_TO (solid gray, arrowed), UPVOTED (faint blue, thin, optional toggle), POSTED_IN_FORUM (no edge — implied by clustering layout).
- Layout: forum/subreddit communities cluster naturally via force-directed; ForceAtlas2 settings tuned for ≤ 50K visible nodes.
- Selection: clicking a User pulls right-panel showing credibility breakdown (Reddit 10-feature or SDN 7-feature per ADR-008), `prescient_correct` count, post + comment timeline.
- Filters (left panel): source type, subreddit, time range, min credibility score, has-school-mention.
- Empty state: "Select a corpus, time range, and optional query above to see the structural graph."

**Performance budget:**
- Initial render of full corpus structural subgraph: < 3 seconds.
- Hover-to-tooltip: < 50ms (preloaded into Sigma's node attributes).
- Zoom / pan: 60fps on Mahyar's GTX 1080.

**What this view never shows:**
- Cluster nodes (Level B).
- Pass-4 sentiment / interview-Q / conflict claims (Level C).
- Cross-graph `SAME_AS` edges (Level C).

This is by contract — the promise to the user is "this view never lies about authorship or threading."

## Level B — `/graph/clusters`

**Source API**: `GET /api/v1/graph/clusters?corpus=...&time_range=...`

**Render rules:**
- Each Cluster = a large circle, sized by member count. Color = sentiment ratio (red < 0.3, gray 0.3–0.7, green > 0.7) once Pass 4 has run; else neutral.
- Cluster label = Pass 3 summary's `label` field. Hover shows full `description`.
- Inter-cluster edges (V1.5: none by default; V1.6 may add SUPPORTS/CONTRADICTS-derived similarity edges).
- Intra-cluster representation: NOT rendered as individual posts. Instead, clicking a cluster opens a side-panel "Posts in this cluster" list with sample posts (sorted by representative score).
- Layout: t-SNE / UMAP projection of cluster centroids, computed server-side once per Pass-3 sweep and cached.
- Filters: corpus, time range, min cluster size, status (`pending_review`, `approved`, `culled`, `auto_approved`).
- Bulk actions toolbar: select N clusters → "Mark for cull" / "Approve for Pass 4" / "Merge into…" / "Split…".

**Cluster-review HITL integration:**
- This view IS the cluster-cull review surface. Each cluster carries a `review_status` chip: pending / approved / culled / merged-into / split.
- A "Submit review batch" button at the top right commits the user's decisions to the HITL queue and triggers the next Pass 4 sweep on approved clusters.
- See `docs/08-ui/hitl-flows.md` for the cluster-cull flow detail (V1.5b deliverable).

**Performance budget:**
- Initial render of ~200 clusters: < 1 second.
- Sample-post panel load: < 300ms.

## Level C — `/graph/analyzed`

**Source API**: `GET /api/v1/graph/analyzed?query=...&source_tier_min=L2&time_range=...&as_of=...&traversal_depth=3&include_anomalies=false`

**Render rules:**
- Full graph. Every node type from V1 + V1.5a (`School`, `Program`, `User`, `Post`, `Comment`, `Topic`, `Cluster`, `Claim`, `L1Document`, `L2Document`, plus cross-graph anchors).
- Edges: every edge type. MENTIONS_SCHOOL, SUPPORTS, CONTRADICTS, SAME_AS, all with bitemporal + rank + tier properties.
- Node coloring by `source_tier`: L1 = gold, L2 = silver, L3 = bronze, L4 = light gray, L5 = dark gray.
- Edge styling by `rank`: preferred = solid + thicker; normal = thinner; deprecated = dashed and faded.
- Status flags rendered as overlays: `invalidated_by_official_data` = red strikethrough; `anomaly` = orange ring; `hitl_pending` = yellow pulse.
- Citation drawer (always-available) — selecting any node/edge populates `references` clickable to source rows / posts / Excel cells.
- Filters: source tier range, rank, status, time range, as-of, has-citation (≥ N), include-anomalies.
- Search bar (top): full-text + alias-aware entity search; selecting a result centers + highlights.

**Cross-graph anchors:**
- A `SAME_AS` edge between an ADEA L1 school and a Reddit-mention school renders as a thick gold link. Selecting it shows both side's evidence side-by-side in the right panel.
- This is the most-used drill-down from per-team dashboards (V1.5c) — clicking a pain-point on the PM dashboard opens this view scoped to the relevant entities.

**Performance budget:**
- Initial render of an entity-scoped 3-hop subgraph: < 2 seconds.
- Path-find / shortest-path interactive: < 500ms.
- Full-corpus render: lazy + paginated (50K nodes visible at a time, more on zoom-in).

## Cross-view conventions

- A node ID is stable across all three views. Selecting `user:reddit:DentalSchool:alice` in Level A and switching to Level C with the keyboard shortcut keeps `alice` selected and centers the analyzed view on her contributions.
- The corpus + time-range + as-of pickers are sticky across views (stored in URL params + local state).
- The view-switcher chip highlights the current view; switching mid-selection keeps selection state.
- Audit-log writes happen on every view load, every selection, every filter change (low-volume events; `kind=view_*`).

## Accessibility (per `docs/08-ui/accessibility.md` requirements)

- Every Sigma.js canvas wrapped with an off-screen aria-live region announcing selection changes.
- Keyboard nav: Tab cycles selectable nodes (ordered by current force-directed layout); Enter activates; Esc clears.
- Color is never the only signal — node-type icons (Material Symbols set) double as shape-and-color encoding.
- Focus visible on every interactive control. WCAG 2.1 AA contrast for all text + chip backgrounds.
- Reduced-motion preference disables ForceAtlas2 animation; snaps to final positions.

## Out of scope for V1.5

- 3D graph viz (Three.js / Reagraph 3D). Sigma.js 2D-only.
- Editing nodes in-canvas (drag to merge, etc.). Edits go through the HITL review surfaces, not direct canvas manipulation.
- Real-time multi-user co-editing (V2 multi-tenant).
- Custom layout algorithms beyond ForceAtlas2 (V1.6 may add radial or hierarchical for the analyzed view).
