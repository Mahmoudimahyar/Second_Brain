# Ingestion Wizards — V1.5a + V1.5b

> Connect-data-source flow IA. Five engines (Postgres, MySQL, SQLite, Neo4j, file-upload). Same wizard skeleton, engine-specific config + sample-row shape.

## Wizard skeleton (five steps)

```
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1 — Pick engine                                            │
│  Route: /ingest/new                                              │
│  Component: EnginePickerGrid (tile UI)                           │
│                                                                  │
│  Tiles: Postgres • MySQL • SQLite • Neo4j • File upload          │
│                                                                  │
│  Click → /ingest/new/{engine}                                    │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────┐
│  STEP 2 — Configure connection                                   │
│  Route: /ingest/new/{engine}                                     │
│  Component: ConnectionConfigForm (engine-specific)               │
│                                                                  │
│  - host / port / database / user (SQL)                           │
│  - file path (SQLite)                                            │
│  - URI (Neo4j)                                                   │
│  - upload area (file)                                            │
│  - CredentialField with plaintext banner (every credential)      │
│  - "Health-check" button (calls /api/v1/sources/healthcheck)     │
│                                                                  │
│  Submit → /ingest/new/{engine}/discover                          │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────┐
│  STEP 3 — Schema discovery                                        │
│  Route: /ingest/new/{engine}/discover?source_id=...               │
│  Component: SchemaTree (mode='preview')                          │
│                                                                  │
│  Streams progress: "Reading information_schema..."                │
│  Renders tables/labels with sampled rows expandable inline        │
│                                                                  │
│  - Per-table preview (sample 100 rows)                            │
│  - FK arrows (SQL) or rel-type chips (Neo4j)                      │
│                                                                  │
│  CTAs: "Refresh discovery" • "Looks good → Map"                   │
│  Submit → /ingest/new/{engine}/mapping                            │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────┐
│  STEP 4 — Mapping (the hardest step)                              │
│  Route: /ingest/new/{engine}/mapping?source_id=...                │
│  Component: SchemaMappingTable + TierSelector                     │
│                                                                  │
│  Table rows: one per discovered table/label                       │
│   Columns:                                                        │
│     - Source name (read-only)                                     │
│     - Mapping type (Node / Edge / Skip) — dropdown                │
│     - Target type — auto-suggested + editable                     │
│     - Properties — per-column mapping (drawer-opened)             │
│     - Confidence — Tremor `ProgressBar` colored by routing band   │
│     - Routing chip — Auto / Review / Reject                       │
│                                                                  │
│  Above the table:                                                 │
│   - Tier selector (default L2; L1 requires confirmation modal)    │
│   - Display name input                                            │
│   - "Bulk accept" / "Bulk skip" / "Reset to suggested"            │
│                                                                  │
│  Submit → POST /api/v1/sources/{id}/mapping/commit                │
│  → /ingest/sources/{id}                                           │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────┐
│  STEP 5 — Connector dashboard (steady state)                     │
│  Route: /ingest/sources/{id}                                     │
│  Components: ConnectorHealthCard + recent pulls table +          │
│              cross-graph link badge + pull-now button            │
│                                                                  │
│  - Health status                                                  │
│  - Last pull stats                                                │
│  - Cross-graph link count + link to /hitl/crosslinks              │
│  - "Pull now" button                                              │
│  - "Edit mapping" / "Disconnect" CTAs                             │
└──────────────────────────────────────────────────────────────────┘
```

## Engine-specific notes

### Postgres / MySQL

- Same form shape: host / port / database / user / SSL toggle / schema filter.
- `CredentialField` for password — placeholder shows env var name (e.g., `PARTNER_DB_PASSWORD`), value stored only in `.env`.
- Health-check runs `SELECT 1` after connecting.
- Schema-filter UI: multi-select of schemas (default just `public`).

### SQLite

- Single field: file path (must be absolute and exist on Mahyar's workstation).
- No credentials.
- Health-check: open + close + read sqlite_master.
- Bonus: pre-filled "Use my V1 L1 side store" quick-link for self-test ingest.

### Neo4j

- Two fields: URI (bolt://...) + database (default `neo4j`) + user.
- `CredentialField` for password.
- Health-check runs `MATCH (n) RETURN count(n) LIMIT 1` after connecting.
- Schema-discovery UX is slightly different: shows labels + relationship types instead of tables + FKs.

### File upload

- Drag-drop zone for `.xlsx`, `.pdf`, `.csv`, `.jsonl`. Multi-file supported.
- Detects file kind via extension + first-bytes inspection.
- Routes to the V1 adapter (l1_excel, l1_pdf, l2_html via converter, l5_reddit if JSONL has Reddit shape, l5_sdn if SDN shape).
- Falls through to L2 generic-document if shape unrecognized.
- No mapping step needed (V1 adapters already canonicalize). Wizard skips Step 4; goes directly Step 3 → Step 5.

## Mapping-wizard UX details

**Confidence routing bands** (matches ADR-014 / ADR-015 thresholds):

| Confidence | Routing chip | UI affordance |
|---|---|---|
| ≥ 0.90 | "Auto" (green) | Pre-checked accept; bulk-accept applies in one click |
| 0.75 ≤ x < 0.90 | "Review" (yellow) | Highlighted row; user must explicitly confirm verdict |
| < 0.75 | "Reject" (red) | Pre-checked `skip`; user can override |

**Per-column property mapping**: clicking a row opens a `Drawer` with a two-column table — source columns on left, target node/edge properties on right. Auto-suggested mappings shown with confidence chips. User can override any row, rename properties, mark "skip this column."

**Tier upgrade modal** (TierSelector L1 click): full modal with:
- Headline: "Mark this source as L1 (immutable ground truth)?"
- Body explaining L1 contract per ADR-014.
- Checkbox: "I confirm this data is immutable ground truth for my domain. Existing L1 nodes from other sources will not be overwritten."
- Button enabled only when checkbox checked.

**Persistence**: every field change debounces (300ms) and saves draft state to localStorage keyed `mapping_draft:{source_id}`. Closing the tab + reopening preserves draft.

**Multi-L1 collision pre-flight**: at commit-time, if mapping would create a multi-L1 collision (per ADR-014 FR-1.5a-4.4), commit blocks with a modal pointing to the conflicting source + offering to resolve via HITL (`multi_l1_claims`) or downgrade this tier.

## Connector dashboard UX details

**`ConnectorHealthCard`** states:
- `healthy` — green dot; "Last pull X minutes ago; N new rows"
- `paused` — gray dot; "Resume" CTA
- `errored` — red dot; error excerpt + retry CTA + "View error log" link
- `pulling` — blue spinner; live progress bar
- `cap_hit` (V1.5c context) — orange; "Web-search cost cap reached" + reset CTA

**Recent pulls table**: paginated; columns = timestamp / mode (delta/full) / rows / nodes / edges / crosslinks / status. Click → pull detail page.

**Cross-graph link badge**: "N pending cross-graph link reviews" → links to `/hitl/crosslinks?source={id}`.

## Errors + recovery

- **Connection failure**: shown inline below the form with engine-specific hint (e.g., "Postgres connection refused — check that port 5432 is reachable").
- **Schema discovery timeout**: shows partial discovery + "Continue with partial" CTA + "Retry" CTA.
- **Mapping commit conflict**: shown as a modal with the conflicting source + decision options.
- **Pull failure mid-flight**: rollback to last consistent state; error excerpt shown in dashboard; retry CTA.

## Accessibility

Every form field labeled, errors associated via `aria-describedby`. Schema-tree expandable nodes have `aria-expanded` state. Schema mapping table fully keyboard-navigable. Per `docs/08-ui/accessibility.md`.
