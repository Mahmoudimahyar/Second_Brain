# Accessibility — V1.5

> Replaces the V1 TBD scaffold. V1.5 commits to **WCAG 2.1 AA** for every operator-facing page. V2's multi-tenant cloud reframe will revisit AAA where viable.

## Requirements (WCAG 2.1 AA baseline)

### Perceivable

- Every interactive control has a visible name (`aria-label`, label association, or visible text).
- Color contrast ratios:
  - Normal text: ≥ 4.5:1.
  - Large text (≥ 18pt or ≥ 14pt bold): ≥ 3:1.
  - UI components + graphical objects: ≥ 3:1.
- Color is never the only signal. Examples in V1.5:
  - Source-tier nodes in Level C carry **both** color (L1=gold, L2=silver, etc.) AND a Material Symbols icon glyph.
  - Status overlays use color + shape (red strikethrough for `invalidated_by_official_data`, orange ring for `anomaly`, yellow pulse for `hitl_pending`).
  - Sentiment in clusters uses color + numeric ratio label (e.g., "0.62 positive" on hover).
- Sigma.js canvas wrapped with an off-screen `aria-live="polite"` region announcing selection changes ("School: New York University College of Dentistry selected").
- All images / icons either decorative (`aria-hidden="true"`) or have meaningful alt text.
- Text resize to 200% does not break any layout.

### Operable

- Every interactive control keyboard-reachable. Tab order matches visual flow.
- Sigma.js keyboard nav:
  - Tab cycles selectable nodes (ordered by current force-directed layout positions).
  - Enter activates / opens detail panel.
  - Esc clears selection.
  - Arrow keys pan; +/- zoom.
- Focus visible on every interactive control (≥ 3px ring, contrast ≥ 3:1 against background).
- No keyboard trap on any modal, drawer, or canvas (Esc dismisses; focus returns to triggering element).
- Skip-link to main content at top of every page.
- Touch target size ≥ 44×44 CSS pixels (mobile-friendly even though V1.5 targets desktop).
- No motion-only feedback. Reduced-motion preference (`prefers-reduced-motion: reduce`):
  - Disables ForceAtlas2 animation in Sigma.js (snaps to final positions).
  - Disables Tremor chart entry animations.
  - Disables sidebar collapse animation.
- Error states announced via `role="alert"` regions, not just toasts.

### Understandable

- Page titles unique and descriptive (`<title>Cluster Review · SecBrain</title>`).
- Form field errors associated with their inputs (`aria-describedby`).
- Form validation messages explicit ("Tier L1 requires confirmation" not "Invalid input").
- Consistent navigation across pages (sidebar layout stable; breadcrumbs always present on nested pages).
- Language declared on `<html lang="en">`.
- Plain-language copy preferred. Technical terms (e.g., "bitemporal", "source tier", "anomaly") link to a glossary tooltip on first appearance per page.

### Robust

- Semantic HTML throughout — no `<div>` where `<button>`, `<nav>`, `<main>` fit.
- All shadcn/ui primitives meet AA in their stock theme; project-wide tweaks (`web/src/components/ui/`) preserve AA.
- ARIA used only where native semantics fall short (e.g., Sigma.js canvas region; bulk-action toolbar with multi-select state).
- Tested with NVDA (Windows) + VoiceOver (macOS, when cross-testing); JAWS not required for V1.5.

## V1.5-specific accessibility cases

| Component | Accessibility consideration |
|---|---|
| `GraphCanvas` | Sigma.js canvas is a `<canvas>` element — invisible to screen readers by default. Wrap with `role="application"` + `aria-label` describing the graph + off-screen `aria-live` for selection. Provide a "View as table" fallback link in the bottom-right that opens a paginated DataTable equivalent. |
| `SchemaMappingTable` | Each row's edit form has labeled fields; per-row save button announces "Mapping saved for table {name}". Bulk-action toolbar exposes selection count via `aria-label="3 of 12 selected"`. |
| `CitationDrawer` | Drawer is a region with `role="region" aria-label="Citations"`. Click-to-source links carry full source description in `aria-label` (post URL is decorative; visible link text is the source's title or post excerpt). |
| `ReviewCard` | Each verdict button has `aria-pressed` reflecting selected state. Notes textarea labeled. Commit button disabled with `aria-disabled` until verdict picked; explanation text linked via `aria-describedby`. |
| `BulkActionToolbar` | Sticky positioning announced; multi-select state communicated via toolbar's `aria-live="polite"` region on count changes. |
| `BitemporalPicker` | `as_of` and `time_range` are two separate ARIA-labeled date inputs with explicit "as of this date" / "from / to" semantics. Calendar pop-overs use shadcn defaults (keyboard accessible). |

## Testing

- **Automated**: axe-core via Playwright on every E2E test. Failing axe = failing test. Target: 0 violations on every page.
- **Manual**: keyboard-only walkthrough of every flow before sub-slice acceptance. Documented in `.agent/reports/v1.5b-a11y-walkthrough.md`.
- **Screen reader**: NVDA (Windows) walkthrough of the four primary flows (ingest wizard, cluster cull, conflict review, PM dashboard drill-down). Documented in same report.
- **Reduced-motion**: every page tested with `prefers-reduced-motion: reduce` simulated.
- **Color blindness**: simulated dichromacy tests on key views (Level A, Level B, Level C; PM dashboard). Per `docs/08-ui/brand-system.md` color palette.

## Out of scope for V1.5

- WCAG 2.1 AAA (V2 candidate).
- Right-to-left layout (V2 if multi-language lands).
- Live captions / audio descriptions (no media in V1.5).
- Cognitive-disability simplification mode (V2 nice-to-have).
- Mobile screen-reader certification (V2 — V1.5 is desktop-first).
