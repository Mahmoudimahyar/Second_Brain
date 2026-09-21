# Component Inventory — V1.5

> Replaces V1 generic-only scaffold. Catalogues the components V1.5b builds, organized by domain. Base primitives come from `shadcn/ui`; KPI/chart panels from `tremor`; graph canvas from `sigma.js`. Custom app components are listed below with their purpose, variants, and pages they appear on.

## Base primitives (shadcn/ui)

Standard set adopted as-is: Button, Input, Textarea, Select, Checkbox, Radio, Switch, Slider, Dialog, Drawer (Sheet), Popover, Tooltip, Toast, Tabs, Accordion, Card, Badge, Avatar, Table (DataTable), DropdownMenu, ContextMenu, Command (Cmd-K palette), Calendar, DatePicker, Form (react-hook-form bindings), Toaster, Skeleton.

Project-wide tweaks via `web/src/components/ui/`: brand colors, focus ring, dense-table preset for graph + audit views.

## Chart primitives (Tremor)

AreaChart, BarChart, LineChart, DonutChart, SparkArea, SparkBar, KpiCard, Metric, ProgressBar, Tracker. Used in `/teams/*`, `/audit`, `/ingest/sources/[id]`, `/`.

## Graph primitives

| Component | Purpose | Variants | Used in |
|---|---|---|---|
| `GraphCanvas` | Sigma.js wrapper with ForceAtlas2 worker, selection state, viewport persistence | `level=A|B|C` controls node/edge styling | `/graph/structural`, `/graph/clusters`, `/graph/analyzed` |
| `GraphFilters` | Left-rail filter stack (tier / time / status / etc.) | `level=A|B|C` controls which filters render | same three pages |
| `GraphSelectionPanel` | Right-rail detail view that reacts to selection | empty / single / multi | same three pages |
| `CitationDrawer` | Bottom-up drawer expanding `references` into clickable source rows | always-on; toggleable | `/graph/analyzed`, `/teams/*` detail pages |
| `MiniMap` | Optional inset of viewport position | optional toggle | all graph pages |
| `EntitySearch` | Search input bound to `query_graph_search` MCP | inline / Cmd-K-modal | top bar, palette |
| `PathFinder` | Picker for two nodes + traversal-depth slider; renders the path subgraph | — | `/graph/analyzed` |

## Ingestion components

| Component | Purpose | Variants | Used in |
|---|---|---|---|
| `EnginePickerGrid` | Tile grid of available engines (Postgres / MySQL / SQLite / Neo4j / Upload) | — | `/ingest/new` |
| `ConnectionConfigForm` | Engine-specific config form with health-check button | per engine | `/ingest/new/[engine]` |
| `CredentialField` | Input + V1.5 plaintext-storage banner + visibility toggle | — | every connection form |
| `SchemaTree` | Collapsible tree of tables/labels with sampled rows | `mode=preview|select|map` | `/ingest/new/[engine]/discover`, `/ingest/new/[engine]/mapping` |
| `SchemaMappingTable` | Per-table row showing suggested node/edge type + confidence + edit affordances | `confidence=auto|hitl|reject` | `/ingest/new/[engine]/mapping` |
| `TierSelector` | Tier picker (L1/L2/L3/L4/L5) with L1-confirmation modal | — | connection forms + connector edit |
| `MappingCommitProgress` | Streaming progress for the commit step | — | `/ingest/new/[engine]/mapping` |
| `ConnectorHealthCard` | Card showing last-pull time, row counts, error state, "Pull now" button | `state=healthy|paused|errored|pulling` | `/ingest`, `/ingest/sources/[id]` |
| `CursorEditor` | Power-user override of the per-table cursor column | — | `/ingest/sources/[id]/edit` |

## HITL components

| Component | Purpose | Variants | Used in |
|---|---|---|---|
| `ReviewQueueHeader` | Counts per item type + batch-mode toggle | — | `/hitl/*` |
| `ReviewCard` | Generic card holding item context + verdict picker + commit button | per item type | every `/hitl/*` page |
| `AliasReviewBody` | Side-by-side mention + candidates with confidence | — | `/hitl/alias` |
| `ConflictReviewBody` | Two-claim comparison + L1 + tier breakdown | — | `/hitl/conflict` |
| `ClusterReviewBody` | Cluster summary + sample posts + verdict (keep/cull/merge/split) | — | `/hitl/clusters` |
| `ProposalReviewBody` | Proposed node/edge type + sample extractions + accept/reject/refine | — | `/hitl/proposals` |
| `CrossLinkReviewBody` | Two-side evidence (DB row + forum mention) | — | `/hitl/crosslinks` |
| `JudgeBreakdown` | Per-vendor judge verdicts for tie-break disagreements | — | `/hitl/judge` |
| `EscalationActionRow` | Pick-winner / re-escalate / send-to-Mahyar | — | `/hitl/escalated` |
| `VerdictPicker` | Standardized verdict + notes input | per item type | inside `ReviewCard` |
| `BulkActionToolbar` | Multi-select bulk verdict actions | — | `/hitl/clusters`, `/hitl/proposals`, `/hitl/crosslinks` |

## Per-team dashboard components

| Component | Purpose | Variants | Used in |
|---|---|---|---|
| `PainPointTable` | Sortable, filterable table of pain points with sentiment + volume | — | `/teams/pm` |
| `PainPointDetailCard` | Full pain-point with citations + proposed feature angles | — | `/teams/pm/[id]` |
| `TrendingTopicCarousel` | Time-windowed trending topics with sentiment heat | — | `/teams/social` |
| `TopicTrendChart` | Volume + sentiment over time | — | `/teams/social/topic/[id]` |
| `SuggestedPostPanel` | LLM-suggested social post angles | — | `/teams/social/topic/[id]` |
| `ContentGapMatrix` | Topic × sentiment cells highlighting gaps | — | `/teams/marketing` |
| `GapDetailPanel` | Single gap with supporting data + suggested content angles | — | `/teams/marketing/gap/[id]` |
| `TeamDashboardLayout` | Shared chrome: header, filters, drill-down sidebar | per-team theming | all `/teams/*` |

## System / shared components

| Component | Purpose | Variants | Used in |
|---|---|---|---|
| `Sidebar` | Persistent collapsible nav | collapsed/expanded | every page |
| `Breadcrumbs` | Auto-generated from route segments | — | every nested page |
| `TopBar` | Corpus picker + time-range + as-of + search + user-menu | — | every page |
| `CommandPalette` | Cmd-K global jump + entity search | — | global |
| `EmptyState` | Standardized empty UI with CTA | per-domain | all index pages |
| `LoadingState` | Skeleton matching the page layout | per-page | all data-loaded pages |
| `ErrorState` | Boundary fallback with retry + link to audit log | per-boundary | global error-boundary |
| `AuditTrail` | Inline expandable audit-log strip on detail pages | — | every detail page |
| `ProvenancePill` | Source tier + rank + confidence chip | — | every node/edge representation |
| `BitemporalPicker` | `as_of` + `time_range` paired control | — | `TopBar` |
| `KbShortcuts` | Always-on tooltip-style hint surface | — | global |

## Rule (carried from V1 scaffold)

If a component appears more than once, it becomes reusable. New domain components go under `web/src/components/[domain]/`; cross-domain components under `web/src/components/shared/`; base primitives are not modified — extend via composition.

## Out of scope for V1.5

- No icon set forked / built — use Lucide React (shadcn default).
- No design tokens system beyond Tailwind config + shadcn theme. Real token system arrives in V2 with multi-tenant theming.
- No drag-and-drop graph editing. Edits go through HITL surfaces, not direct canvas manipulation.
- No virtualized infinite scroll outside DataTable's built-in. Pagination is preferred.
