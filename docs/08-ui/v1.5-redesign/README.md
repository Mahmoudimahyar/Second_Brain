# V1.5 UI Redesign — Index

> Comprehensive UI redesign package. Authored 2026-05-25 in response to "the UI looks bad." Supersedes the visual-design portions of `docs/08-ui/` (information architecture in `page-inventory.md` / `site-map.md` / `navigation-map.md` is preserved; brand-system / design-system / asset-library / accessibility are superseded by docs in this directory).

## What's in this folder

| # | File | Purpose |
|---|---|---|
| 00 | `00-design-critique.md` | What's broken in the current implementation + priority recommendations |
| 01 | `01-design-system.md` | Aurora palette, typography, spacing, motion, libraries, full visual system |
| 02 | `02-data-source-journeys.md` | Per-source UX (Postgres, MySQL, SQLite, Neo4j, Reddit, SDN, file upload, website V1.6) |
| 03 | `03-graph-visualization.md` | Sigma.js canvas spec for Levels A/B/C + cross-graph |
| 04 | `04-processing-states.md` | Unprocessed → processing → intermediate → done UI; ETA computation; SSE streaming |
| 05 | `05-trust-tier-ux.md` | How users see, understand, and change trust tiers |
| 06 | `06-hero-page-designs.md` | Full specs for the six most-used pages (Home, Ingest, Cluster Cull, Conflict, Level C, PM Dashboard) |
| 07 | `07-component-vocabulary.md` | All 84 components organized by domain, with props + variants |
| 08 | `08-motion-language.md` | Framer Motion patterns, durations, easing, reduced-motion |
| 09 | `09-accessibility.md` | WCAG 2.1 AA commitments; supersedes `docs/08-ui/accessibility.md` for the redesign |
| 10 | `10-libraries-and-install.md` | Plug-and-play library picks + exact install order + bundle budget |

## How to read this package

**Start with `00-design-critique.md`** — it explains why the redesign is necessary.

**Then `01-design-system.md`** — the visual identity. Read this end-to-end; it's the single most important document.

**Then pick the area you're working on**:
- Backend / data source work → `02-data-source-journeys.md` + `04-processing-states.md`.
- Graph canvas work → `03-graph-visualization.md`.
- Trust tier UX → `05-trust-tier-ux.md`.
- Building specific pages → `06-hero-page-designs.md`.
- Building components → `07-component-vocabulary.md`.
- Animations → `08-motion-language.md`.
- Accessibility → `09-accessibility.md`.
- Setting up the build → `10-libraries-and-install.md`.

## Relationship to existing docs

| Existing doc | Status |
|---|---|
| `docs/08-ui/brand-system.md` | **Superseded** by `01-design-system.md`. Stay-on-shadcn-defaults reversed; Aurora palette adopted. |
| `docs/08-ui/design-system.md` | **Superseded** by `01-design-system.md` + `07-component-vocabulary.md`. |
| `docs/08-ui/asset-library.md` | **Mostly preserved**. Lucide is still the primary icon library; Tabler added as secondary. No custom logos still. |
| `docs/08-ui/accessibility.md` | **Superseded** by `09-accessibility.md`. WCAG 2.1 AA commitment unchanged; details tightened. |
| `docs/08-ui/component-inventory.md` | **Superseded** by `07-component-vocabulary.md`. |
| `docs/08-ui/graph-level-views.md` | **Superseded** by `03-graph-visualization.md`. ADR-012 contracts unchanged. |
| `docs/08-ui/hitl-flows.md` | **Mostly preserved**; this redesign adds visual + motion details for each flow. |
| `docs/08-ui/ingestion-wizards.md` | **Mostly preserved**; this redesign adds full per-source journey detail in `02-data-source-journeys.md`. |
| `docs/08-ui/page-inventory.md` | **Preserved**. Information architecture unchanged; this redesign re-skins the existing routes. |
| `docs/08-ui/site-map.md` | **Preserved**. |
| `docs/08-ui/navigation-map.md` | **Preserved**. |

## Implementation prompt

A standalone prompt for a coding agent (Claude Code) to rebuild the UI against this design package: see `PROMPTS/V1.5_UI_REDESIGN_PROMPT.md` (separate file).

## Sub-slice gating

The redesign is treated as **V1.5d** (a fourth sub-slice after V1.5a/b/c). Same TDD discipline applies. Gate report at `.agent/reports/v1.5d-redesign-slice.md` before declaring V1.5 visually complete.

Estimated effort: ~5 focused weeks per `10-libraries-and-install.md` §4.
