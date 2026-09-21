# Component Vocabulary — Full Spec

> Every component the redesign requires, organized by domain. Each entry: name, purpose, props, variants, key visual rules, dependencies. The 23 shadcn primitives form the base; everything else is documented here.

## 0. Layering

```
┌────────────────────────────────────────────────────────────┐
│  Page-level layouts                                        │
│  (DashboardLayout, FormLayout, GraphLayout)               │
├────────────────────────────────────────────────────────────┤
│  Domain components                                         │
│  (Graph, Ingest, HITL, Team)                              │
├────────────────────────────────────────────────────────────┤
│  Shared molecules                                          │
│  (TierBadge, ProvenancePill, TrustMeter, ...)             │
├────────────────────────────────────────────────────────────┤
│  shadcn/ui primitives                                      │
│  (Button, Input, Card, Dialog, ...)                       │
└────────────────────────────────────────────────────────────┘
```

Files structure:

```
web/src/components/
  ui/              # shadcn primitives — run `shadcn add` to populate
  shared/          # cross-domain molecules
  ingest/          # ingestion-wizard components
  hitl/            # review-flow components
  graph/           # graph canvas + selection panels
  team/            # PM/Social/Marketing dashboard components
  layouts/         # page layout wrappers
```

---

## 1. shadcn primitives (run `shadcn add`)

These 23 are non-negotiable foundation. Per `01-design-system.md` §12.

| Component | shadcn name | Use |
|---|---|---|
| Button | button | Primary / Secondary / Ghost / Destructive / Link variants |
| Input | input | Default + sized variants |
| Textarea | textarea | Multi-line input |
| Label | label | Form field label |
| Form | form | Compositional form helpers + Form.Item, Form.Control, Form.Message |
| Select | select | Single-select dropdown |
| Checkbox | checkbox | Boolean input |
| Radio Group | radio-group | Single-select group |
| Switch | switch | Toggle |
| Slider | slider | Range input |
| Dialog | dialog | Modal |
| Sheet | sheet | Side drawer (left/right/top/bottom) |
| Drawer | drawer | (Vaul wrapper) Mobile-friendly bottom drawer |
| Popover | popover | Floating content |
| Tooltip | tooltip | Hover hint |
| Tabs | tabs | Tab navigation |
| Accordion | accordion | Collapsible sections |
| Card | card | Container with optional header/footer |
| Badge | badge | Small inline tag |
| Avatar | avatar | User image / initials fallback |
| DropdownMenu | dropdown-menu | Action menu |
| ContextMenu | context-menu | Right-click menu |
| Command | command | Cmd-K palette |
| Calendar | calendar | Date picker |
| Skeleton | skeleton | Loading placeholder |
| DataTable | custom (see below) | TanStack Table integration |

### DataTable

Custom shadcn-style data table on TanStack Table. Lives in `web/src/components/ui/data-table.tsx`.

Features:
- Virtual scroll for > 1000 rows.
- Column visibility toggle.
- Column resize.
- Sortable columns.
- Filterable columns.
- Row selection (single + multi).
- Sticky header.
- Empty state slot.

Used in: HITL queue, audit log, source dashboards.

---

## 2. Shared molecules (`web/src/components/shared/`)

### TierBadge

Per `05-trust-tier-ux.md` §1.

```tsx
<TierBadge tier="L1" size="sm" iconOnly={false} detailed={false} />
```

Props:
- `tier: 'L1' | 'L2' | 'L3' | 'L4' | 'L5'`
- `size: 'sm' | 'md' | 'lg'` — 12/14/16 px font
- `iconOnly: boolean` — hide label
- `detailed: boolean` — hover tooltip with full description

Visual: rounded chip with tier-color border + lighter background + glyph + label. ARIA: `role="status"` + `aria-label="Source tier {tier}"`.

### ProvenancePill

Per `05-trust-tier-ux.md` §2.

```tsx
<ProvenancePill
  tier="L1"
  rank="preferred"
  confidence={0.95}
  referenceCount={3}
  onClickReferences={(refs) => openCitationDrawer(refs)}
/>
```

Inline rendering with TierBadge + rank chip + confidence dot + ref-count link.

### TrustMeter

Per `05-trust-tier-ux.md` §3.

```tsx
<TrustMeter
  tier="L1"
  rank="preferred"
  haloDecay={0.92}
  credibility={0.98}
  // computes final score = tier × rank × decay × credibility
/>
```

Visx horizontal-bar widget. Animated entry (200ms ease-out per bar; 50ms stagger).

### ConfidenceDial

For HITL review cards.

```tsx
<ConfidenceDial value={0.84} band="hitl" size={64} />
```

Circular progress ring (visx Arc). Color from confidence band (green/amber/red). Label inside the ring shows value.

### ConfidenceChip

Inline confidence indicator:

```tsx
<ConfidenceChip value={0.92} />  →  [● 0.92]   (green dot, in success color)
```

### CitationDrawer

Bottom-up drawer (Vaul) showing references for the currently-selected entity.

```tsx
<CitationDrawer
  entityId="school:nyu_dental"
  references={refs}
  open={open}
  onOpenChange={setOpen}
/>
```

Always accessible from the bottom-right of every page where an entity can be selected.

### TimelineSpark

Bitemporal mini timeline for selection panels.

```tsx
<TimelineSpark
  events={[
    { ts: '2024-05-22T14:21Z', label: 'Pass 1 done' },
    { ts: '2024-05-22T14:23Z', label: 'Pass 2 done' },
    ...
  ]}
  current="2024-05-22T15:09Z"
/>
```

Horizontal mini-timeline; dots for events; tooltip on hover with full label + timestamp.

### AuditTrail

Inline expandable audit log on detail pages.

```tsx
<AuditTrail entityId="school:nyu_dental" maxRows={5} expandable />
```

Loads via `/api/v1/audit?entity={id}` with TanStack Query. Renders as a compact list inside a `<details>` element by default.

### JourneyRail

Per `02-data-source-journeys.md` §0.

```tsx
<JourneyRail
  steps={[
    { id: 'intake', label: 'Intake', status: 'done', href: '...' },
    ...
  ]}
/>
```

Horizontal step indicator. Pills + connecting lines. Pulse on active step. Click to navigate to completed steps.

### KbShortcutsOverlay

Always-on `?` icon in bottom-right; press `?` to expand a modal listing all shortcuts active on the current page.

```tsx
<KbShortcutsOverlay
  shortcuts={[
    { keys: 'Cmd+K', label: 'Open command palette' },
    { keys: 'J', label: 'Next item' },
    ...
  ]}
/>
```

### CommandPalette

Cmd-K palette using shadcn's Command primitive + cmdk under the hood.

```tsx
<CommandPalette
  open={open}
  onOpenChange={setOpen}
  recentSearches={recent}
  shortcuts={pageShortcuts}
/>
```

Sections:
- Recent searches.
- Pages (navigate to any route).
- Actions (e.g., "Pull source", "Run Pass 4", "Toggle theme").
- Entity search (full-text + alias-aware via `/api/v1/graph/search`).

### ThemeToggle

Light / dark / system. Sits in top-right of TopBar.

```tsx
<ThemeToggle />  // uses next-themes
```

### EmptyState

Standardized empty UI.

```tsx
<EmptyState
  icon={<DatabaseZap className="size-12" />}
  title="No sources connected"
  description="Connect your first source to get started."
  primaryAction={{ label: "Connect", href: "/ingest/new" }}
  secondaryAction={{ label: "Read docs", href: "/docs" }}
/>
```

### LoadingState

Skeleton wrapper that matches layout. Composable from shadcn `Skeleton`.

```tsx
<LoadingState variant="card-list" rows={5} />
<LoadingState variant="table" rows={10} cols={6} />
<LoadingState variant="graph" />
<LoadingState variant="dashboard" />
```

### ErrorState

```tsx
<ErrorState
  title="Something broke"
  description="The graph store didn't respond."
  primaryAction={{ label: "Retry", onClick: retry }}
  secondaryAction={{ label: "Audit log", href: "/audit" }}
  technical={error.message}  // collapsible details
/>
```

### Sidebar + TopBar

Per `01-design-system.md` §10. Already exist as scaffolds in the codebase; this redesign rewrites them with:
- Icons on Sidebar nav (Lucide).
- Sidebar collapse to icon-only mode.
- TopBar has corpus picker, time range picker, as-of picker, EntitySearch + CommandPalette trigger, ThemeToggle, KbShortcutsOverlay button.

### Breadcrumbs

```tsx
<Breadcrumbs items={[{ label: 'Ingest', href: '/ingest' }, ...]} />
```

Auto-generated by Next.js layout chain or manually constructed per page.

---

## 3. Ingest components (`web/src/components/ingest/`)

### EnginePickerGrid

Tile grid on `/ingest/new`. Each tile: engine icon (Tabler), engine name, brief description, "live tier" badge (L1/L2/L5 hint).

### ConnectionConfigForm

Engine-specific form. Wrapped in `<Form>` (shadcn + react-hook-form + zod resolver).

Props:
- `engine: 'postgres' | 'mysql' | 'sqlite' | 'neo4j' | 'upload'`
- `defaultValues?: Partial<EngineConfig>`
- `onSubmit: (values: EngineConfig) => Promise<void>`

Renders engine-specific fields per `02-data-source-journeys.md` §1-§5.

### CredentialField

Composition of shadcn `Input` (type=password) + visibility toggle + plaintext-storage banner.

```tsx
<CredentialField
  envVarRef="PARTNER_DB_PASSWORD"
  required
  helpText="Stored in plaintext .env per V1.5 policy"
/>
```

### SchemaTree

Collapsible tree on the discover page. Wraps `@radix-ui/react-collapsible`.

```tsx
<SchemaTree
  snapshot={schemaSnapshot}
  mode="preview"  // 'preview' | 'select' | 'map'
  onTableSelect={(table) => setSelected(table)}
/>
```

### SchemaMappingTable

Per `06-hero-page-designs.md` §2 page 3. TanStack Table with editable cells.

```tsx
<SchemaMappingTable
  proposal={mappingProposal}
  onCellEdit={(rowId, field, value) => updateDecision(rowId, field, value)}
  onBulkAction={(action) => applyBulk(action)}
/>
```

### TierSelector

Per `05-trust-tier-ux.md` §5.

```tsx
<TierSelector
  value={tier}
  onChange={setTier}
  l1RequiresConfirmation
  onL1ConfirmationOpen={() => setConfirmOpen(true)}
/>
```

### MappingCommitProgress

Streaming progress bar shown during `commit_mapping` execution.

### ConnectorHealthCard

KPI card showing connector status + last pull + node/edge counts. Used on `/ingest/sources/[id]`.

```tsx
<ConnectorHealthCard
  sourceId={id}
  status="active"
  lastPullAt={...}
  rowsTotal={10234}
  nodesTotal={1247}
  edgesTotal={3421}
  crossLinks={53}
  onPullNow={() => mutatePullNow()}
/>
```

### CursorEditor

Power-user override for the per-table cursor column.

```tsx
<CursorEditor
  sourceId={id}
  cursors={cursorState}
  onChange={updateCursors}
/>
```

### EngineIcon

Tabler icon mapping for each supported engine.

```tsx
<EngineIcon engine="postgres" className="size-5" />
```

---

## 4. HITL components (`web/src/components/hitl/`)

### ReviewQueueHeader

Counts per item type + bulk-mode toggle.

```tsx
<ReviewQueueHeader
  counts={{ alias: 3, conflict: 2, cluster: 18, proposal: 7, ... }}
  bulkMode={bulkMode}
  onBulkModeToggle={setBulkMode}
/>
```

### ReviewCard

Generic chrome wrapping per-type body.

```tsx
<ReviewCard
  itemType="conflict"
  itemId="conflict:abc123"
  progress={{ current: 1, total: 2 }}
  onPrevious={prev}
  onNext={next}
  onCommit={commit}
  onDefer={defer}
  onEscalate={escalate}
>
  <ConflictReviewBody item={item} />
</ReviewCard>
```

### Per-type bodies

- `AliasReviewBody` — mention + top-K candidates with similarity scores.
- `ConflictReviewBody` — two claim cards side-by-side + system resolution + override.
- `ClusterReviewBody` — cluster label + sample posts + verdict.
- `ProposalReviewBody` — proposed type + sample extractions + accept/reject/refine.
- `MultiL1ReviewBody` — two L1 sources' conflicting claims + pick winner.
- `CrossLinkReviewBody` — side-by-side evidence + tier badges + accept/reject.
- `JudgeBreakdown` — 3-vendor judge verdicts + per-vendor reasoning.
- `WebSearchDisagreementBody` — 3-signal table (A/B/C) + raw Tavily responses.
- `TavilyUnavailableBody` — original claim + retry options.

### VerdictPicker

Standardized verdict + notes input.

```tsx
<VerdictPicker
  itemType="conflict"
  verdicts={['accept_a', 'accept_b', 'temporal_split', 'escalate']}
  value={verdict}
  onChange={setVerdict}
  showNotes
/>
```

### BulkActionToolbar

Sticky toolbar appears when ≥ 1 selection on a queue.

```tsx
<BulkActionToolbar
  selectedCount={5}
  totalCount={18}
  actions={[
    { id: 'approve', label: 'Approve all', shortcut: 'A' },
    { id: 'reject', label: 'Reject all', shortcut: 'R' },
    ...
  ]}
  onAction={handleAction}
/>
```

### ClaimCard

Single-claim renderer. Used inside ConflictReviewBody, MultiL1ReviewBody, etc.

```tsx
<ClaimCard
  claim={claim}
  emphasis="winner"  // 'winner' | 'loser' | 'neutral'
/>
```

Renders TierBadge + ProvenancePill + ConfidenceDial + claim body + source link.

### EscalationActionRow

Bottom-of-card row for escalation flows.

---

## 5. Graph components (`web/src/components/graph/`)

### GraphCanvas

Per `03-graph-visualization.md`. Sigma.js wrapper.

```tsx
<GraphCanvas
  level="A" | "B" | "C"
  query={query}
  filters={filters}
  selection={selection}
  onSelectionChange={setSelection}
  layout="force"   // 'force' | 'hierarchical' | 'radial'
/>
```

### GraphFilters

Left-rail filter stack. Level-specific.

```tsx
<GraphFilters level="C" filters={filters} onChange={setFilters} />
```

### GraphSelectionPanel

Right-rail detail view.

```tsx
<GraphSelectionPanel selection={selection} onClose={clearSelection} />
```

### MiniMap

Top-right inset.

```tsx
<MiniMap canvas={canvasRef} />
```

### EntitySearch

Top-bar search input + Cmd-K palette entity-search section.

### PathFinder

Picker for two nodes + traversal-depth slider; renders the path subgraph.

### LayoutPicker

Picker for force / hierarchical / radial layouts on graph views.

### LegendPanel

Collapsible legend explaining node shapes + edge styles + tier colors. Always available; collapsible.

---

## 6. Team components (`web/src/components/team/`)

### TeamDashboardLayout

Shared chrome for PM / Social / Marketing.

```tsx
<TeamDashboardLayout
  team="pm" | "social" | "marketing"
  filters={filters}
  onFiltersChange={setFilters}
  kpiStrip={<KpiStrip ... />}
>
  {children}
</TeamDashboardLayout>
```

### PainPointTable

```tsx
<PainPointTable
  painPoints={painPoints}
  onRowClick={(pp) => navigate(`/teams/pm/${pp.id}`)}
/>
```

Each row uses a `PainPointRow` sub-component with sparkline, tier-mix bar, sentiment chip.

### PainPointDetailCard

Drill-down detail page content.

### TrendingTopicCarousel

Card carousel of trending topics. Magic UI's `<Marquee>` for the scrolling case; standard cards otherwise.

### TopicTrendChart

Tremor LineChart for time-window topic volume + sentiment.

### SuggestedPostPanel

Side panel with LLM-generated post angles + Draft watermark + copy-to-clipboard.

### ContentGapMatrix

visx 2D heatmap: topics × sentiment cells, colored by volume.

### GapDetailPanel

Single-gap detail.

### SuggestedAnglesPanel

Shared component across all three teams. Shows angles with Draft watermark.

```tsx
<SuggestedAnglesPanel
  team="pm"
  itemId={painPointId}
  k={3}
  model="gemini-2.5-flash-lite"
/>
```

### TierMixBar

Stacked horizontal bar showing tier composition of an insight.

```tsx
<TierMixBar
  composition={{ L1: 0.20, L2: 0.04, L3: 0, L4: 0, L5: 0.76 }}
  width={200}
/>
```

### MiniSparkline

Tremor `SparkArea` wrapper for trend indicators.

---

## 7. Layout components (`web/src/components/layouts/`)

### AppShell

The whole-app chrome.

```tsx
<AppShell>
  <Sidebar />
  <div className="flex flex-col">
    <TopBar />
    <main>{children}</main>
  </div>
</AppShell>
```

### DashboardLayout

Used by Home, Connector Dashboard, PM/Social/Marketing.

```tsx
<DashboardLayout
  title="..."
  description="..."
  breadcrumbs={[...]}
  primaryAction={{ label: "...", onClick: ... }}
>
  {children}
</DashboardLayout>
```

### FormLayout

Used by Connect wizards, Settings pages.

```tsx
<FormLayout
  title="..."
  steps={[...]}  // for JourneyRail
  currentStep={2}
>
  {children}
</FormLayout>
```

### GraphLayout

Full-width, sidebar collapsible.

```tsx
<GraphLayout>
  <GraphFilters />
  <GraphCanvas />
  <GraphSelectionPanel />
  <CitationDrawer />
</GraphLayout>
```

### ReviewLayout

For HITL pages.

```tsx
<ReviewLayout
  itemType="conflict"
  progress={{ current: 1, total: 2 }}
>
  {children}
</ReviewLayout>
```

---

## 8. Naming + file conventions

- Component files: `PascalCase.tsx`. One component per file (except trivial sub-components).
- Hooks: `useCamelCase.ts` in `web/src/hooks/`.
- Types: co-located with the component OR centralized in `web/src/types/`.
- Stories (V1.6 with Storybook): `Component.stories.tsx` alongside.
- Tests: `Component.test.tsx` alongside.

## 9. Component testing

- Vitest + React Testing Library for unit (renders, props, basic interactions).
- Playwright for E2E (page-level flows).
- axe-core in Playwright (a11y).
- Visual regression: V1.6 candidate with Percy / Chromatic.

## 10. Bundle budget per component family

| Family | Max gzipped per route |
|---|---|
| Shared molecules | 30 KB |
| Ingest (only on /ingest) | 40 KB |
| HITL (only on /hitl) | 40 KB |
| Graph (only on /graph) | 90 KB (Sigma + graphology) |
| Team (only on /teams) | 50 KB (Tremor charts) |

Lazy-load via Next.js dynamic imports for graph + team families.

## 11. Component count summary

| Family | Components |
|---|---|
| shadcn primitives | 23 |
| Shared molecules | 15 |
| Ingest | 9 |
| HITL | 13 (10 review bodies + 3 chrome) |
| Graph | 8 |
| Team | 11 |
| Layouts | 5 |
| **Total** | **84** |

Of these, the V1.5 implementation has:
- 23 shadcn primitives: 0 (directory empty)
- Shared: 4 of 15 (Sidebar, TopBar, QueryProvider, ReviewPage)
- Ingest: 0 of 9
- HITL: 0 of 13
- Graph: 1 of 8 (GraphResults — fallback table)
- Team: 0 of 11
- Layouts: 0 of 5

**Gap: 76 components missing.** This is what the redesign implementation must build.
