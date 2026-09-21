# UI Flow — V1.6a Website-Crawl Ingestion

Five pages, all under `/ingest/web/*`. Reuses V1.5b's `IngestionLayout`, `CitationDrawer`, `CronPicker` (extends), `AuditTimeline`, and `TremorBarChart`.

## Page inventory

| Route | Purpose |
|---|---|
| `/ingest/web` | Domain list + global status |
| `/ingest/web/register` | New-domain wizard (6 steps) |
| `/ingest/web/[domain]` | Domain detail (settings + history + entities + clusters) |
| `/ingest/web/[domain]/page/[id]` | Single-page detail with bitemporal timeline |
| `/ingest/web/[domain]/settings` | Per-domain settings editor (split off from detail to avoid overload) |

Plus extensions:
- `/settings/web-search` (V1.5c) gains a "Crawl proxy" tab for ScrapingBee.

## Page 1 — `/ingest/web` (domain list)

### Goals
Show every registered domain at a glance. Surface "is anything broken?" + "is anything overrunning budget?".

### Components
- Header: "Website crawls" + button "Register domain →".
- Quick-stats row: total domains / active / paused / month spend / month cap.
- Tremor `BarChart` (last 30 days, stacked by domain) of `crawl_cost` rows.
- Table:
  | Domain | Tier | Stage | Cadence (humanized) | Status | Pages | Last run | Next run | Budget | Actions |
  | adea.org | L2 | L1 | Daily 06:00 UTC | ● Active | 1,247 | 2026-05-26 06:01 | 2026-05-27 06:00 | $2.10 / $5.00 (42%) | Run / Pause / Edit / Delete |

- Empty state: "No domains registered yet" + CTA → `/ingest/web/register`.
- HITL banner if any `crawl_cap_hit` / `crawl_chronic_failure` items pending.

### Actions
- Click "Register domain" → wizard.
- Click row → `/ingest/web/[domain]`.
- "Run now" → POST `/api/v1/ingest/web/domains/{id}/run-now`; toast on success.
- "Pause" / "Resume" → confirm modal → POST pause/resume.
- "Edit" → `/ingest/web/[domain]/settings`.
- "Delete" → confirm modal ("This stops future crawls. Audit history preserved.") → DELETE.

## Page 2 — `/ingest/web/register` (wizard)

Six steps, one screen each with progress bar + Back/Next.

### Step 1 — URL
- Input: domain URL (e.g. `https://www.adea.org/`).
- On Next: validate FQDN parseable + check `blocked_domains.FORUM_DOMAINS` ∪ `SOCIAL_DOMAINS` + run health check.
- Inline errors:
  - `DOMAIN_BLOCKED` → "This domain is on the forum/social-media blocklist. Forums have their own ingestion path (see Reddit/SDN setup)."
  - `UNREACHABLE_DOMAIN` → "Couldn't reach `<domain>` (status: 503). Try again later or check the URL."

### Step 2 — Tier
- Radio: L2 (default) / L1 (advanced).
- L1 selection reveals warning + checkbox: "I confirm this domain produces immutable ground truth (e.g. official regulatory data) and conflicts with existing L1 cause HITL escalation."

### Step 3 — Stage
- Three cards: L0 / L1 / L2 with brief description + cost preview.
- L2 card shows: "Estimated cost: $0.001/page × ~500 pages/run × 30 runs/month ≈ $15/month. Default cap $5 will throttle to L0+L1 after first ~10 days." (numbers fed from V1.5c cost-estimator).
- Default: L1.

### Step 4 — Cadence
- `CronPicker` component:
  - Preset buttons: Hourly / Daily 06:00 UTC / Weekly Mon 06:00 / Monthly 1st 06:00 / Custom.
  - Custom mode reveals raw cron field with live `croniter` validation + next-3-runs preview.

### Step 5 — Budget + options
- `max_pages_per_run` (slider 50–10,000).
- `max_pages_per_month` (slider 100–1,000,000).
- `max_usd_per_month` (input, range 0–10,000).
- `concurrency` (1–16; slider).
- `enable_ocr` (toggle, off by default).
- `enable_scrapingbee` (toggle, off by default; shows warning if no key configured → link to `/settings/web-search`).

### Step 6 — Review + confirm
- Summary card with every choice from steps 1–5.
- "Register & start first crawl" CTA → POST `/api/v1/ingest/web/domains` → if success, navigate to `/ingest/web/[domain]` with `?just_registered=1` (shows banner "Crawl scheduled for {next_run_at} — or click Run now to start immediately.").

## Page 3 — `/ingest/web/[domain]` (detail)

### Header
- Domain + tier + stage badges.
- Status pill.
- Action buttons: Run now / Pause-Resume / Edit settings / Delete.

### Sections (tabs)

**Overview**
- Cost chart (last 30 days) + budget gauge.
- Last 5 runs table (status + pages_fetched + duration + cost).
- Top 10 changes in the last run (URL + change-type: added/changed/removed).

**History**
- Full `crawl_jobs` table with status filter + date range.
- Click row → expanded JSON view + Prefect run link.

**Pages**
- Searchable / filterable table of all `pages_index` rows.
- Columns: URL / mime / first_seen / last_seen / version_count.
- Click → `/ingest/web/[domain]/page/[id]`.

**Entities (L1 only)**
- Tremor `BarChart` top 20 mentioned entities by mention count.
- Click → V1.5b `/graph/structural` centered on that entity.

**Clusters (L2 only)**
- List of `Cluster` nodes ordered by member count.
- Click → V1.5b `/graph/clusters` centered.

**Settings link**
- Button → `/ingest/web/[domain]/settings`.

## Page 4 — `/ingest/web/[domain]/page/[id]`

### Sections
- Rendered Markdown body (from L1 Trafilatura extraction).
- Source URL with "Open in browser" link.
- Bitemporal version timeline: horizontal stripe with version markers; click marker → load that version's body.
- LINKS_TO targets (collapsed by default, expandable list).
- Mentioned entities (if L1 run): chip list, click to `/graph/structural`.
- Raw fetched payload download button (HTML/PDF/etc.).
- Audit timeline (fetched by `/api/v1/ingest/web/pages/{id}/history`).

## Page 5 — `/ingest/web/[domain]/settings`

Same fields as register wizard Step 5, but as a flat form. Special handling:
- Tier change L2 → L1 reveals confirm_l1 checkbox.
- Stage change L2 → L0/L1 reveals `purge stage data?` modal (optional).
- Cron change shows next-3-runs preview.
- Save → PATCH `/api/v1/ingest/web/domains/{id}`.

## Extension — `/settings/web-search` (V1.5c)

Add a "Crawl proxy" tab to the existing V1.5c web-search settings page. Fields:
- ScrapingBee API key (`CredentialField`; plaintext .env per V1.5).
- Health-check button → POST `/api/v1/ingest/web/settings/scrapingbee/health`.
- Last 30 days ScrapingBee cost (from `crawl_cost` where `kind='scrapingbee'`).
- Per-domain table showing which domains have `enable_scrapingbee=true`.

## Accessibility

Every page passes `axe-core` checks:
- Keyboard-navigable wizard with arrow-key step nav and ESC to cancel.
- Status pills carry `aria-label` for screen readers (e.g. "Active. Last run succeeded.").
- All buttons have visible focus rings.
- Color-blind-safe palette (Tremor defaults, verified against deuteranopia simulation).
- Form errors announced via `aria-live="polite"`.

## Empty / error states (catalog)

| Context | State |
|---|---|
| No domains registered | Hero CTA → wizard |
| Domain with zero runs | "Scheduled for {next_run_at}. Or run now." |
| Domain at L0 with no entities | "Upgrade to L1 to extract entities (no LLM cost)." |
| Domain at L1 with no L2 clusters | "Upgrade to L2 to extract clusters and claims (LLM cost applies)." |
| Domain `auto_paused` | Banner: "Auto-paused after 5 failed runs. See HITL queue → Resume manually." |
| Domain `budget_capped` last run | Banner: "Budget cap hit mid-run. L0+L1 saved; L2 deferred. Raise cap to continue." |
| 404 page id | "Page not found in this domain's index." |

## UI test coverage

Playwright spec `web/e2e/ingest-web.spec.ts` covers:
1. Registration wizard happy path (3 seed domains).
2. Registration wizard blocked-domain path (`reddit.com` → 422 inline error).
3. Registration wizard L1 path with confirm checkbox.
4. Pause/Resume round-trip.
5. Delete with confirmation.
6. Run-now → status polls to succeeded.
7. Page detail bitemporal-version-click loads prior body.
8. L0 only domain shows "Upgrade to L1" empty state on Entities tab.
9. Budget cap hit shows banner + HITL CTA link.
10. ScrapingBee health check from `/settings/web-search` → green/red badge.
