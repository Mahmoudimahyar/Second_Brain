# Accessibility Plan — Redesign

> Supersedes `docs/08-ui/accessibility.md` for the V1.5 redesign. WCAG 2.1 AA committed.

## 0. Commitments

1. **WCAG 2.1 AA across every operator-facing page**. Verified by axe-core in CI.
2. **Color is never the only signal**. Tier, status, rank, and confidence all have shape + icon + text alternatives in addition to color.
3. **Every flow keyboard-only completable**. No mouse required for any task.
4. **Screen-reader (NVDA on Windows) walkthrough validated** before each sub-slice gate.
5. **Reduced-motion respected** for every motion > 100ms.
6. **No accessibility violation tolerated**. CI gate fails on any axe-core violation.

## 1. Audit cadence

- axe-core runs in every Playwright test (automatic).
- NVDA walkthrough of the four primary flows before each sub-slice acceptance:
  - Connect a Postgres source → discover → map → commit (Ingest journey).
  - Review a cluster batch + commit (Cluster cull).
  - Resolve a conflict (Conflict review).
  - Drill down on a PM pain point (Team dashboard).
- Manual keyboard-only walkthrough of every page that ships.
- Color-blindness simulation (Chrome DevTools) on Level A/B/C views + PM/Social/Marketing dashboards.

## 2. Perceivable

### Color contrast

| Surface | Background | Foreground | Ratio | Pass? |
|---|---|---|---|---|
| Body text | `--background` | `--foreground` | ≥ 16:1 (dark mode), ≥ 17:1 (light mode) | ✅ AAA |
| Muted text | `--background` | `--muted-foreground` | ≥ 4.5:1 | ✅ AA |
| Border on surface | `--surface` | `--border` | ≥ 1.5:1 | ✅ visual minimum |
| Primary button | `--primary` | `--primary-foreground` | ≥ 4.5:1 | ✅ AA |
| Accent on surface | `--surface` | `--accent` | ≥ 4.5:1 large; verify small text | ⚠ verify |
| Tier badges (each tier) | `--tier-l{n}-bg` | `--tier-l{n}-fg` | ≥ 4.5:1 | ✅ designed for AA |
| Destructive | `--background` | `--destructive` | ≥ 4.5:1 | ✅ |
| Status overlays (red strike, orange ring, yellow pulse) | various | various | ≥ 3:1 for non-text | ✅ |

All passes verified by axe-core in the Playwright suite.

### Non-color signals

| Semantic | Color | Shape/Icon | Text |
|---|---|---|---|
| Tier L1 | Gold | Star glyph | "L1" label |
| Tier L2 | Teal | Open book | "L2" |
| Tier L3 | Violet | Bookmark | "L3" |
| Tier L4 | Zinc | Globe | "L4" |
| Tier L5 | Rose | Speech bubble | "L5" |
| Confidence auto-accept | Green | Solid dot | "Auto" / "0.92" |
| Confidence HITL | Amber | Half-filled dot | "Review" / "0.84" |
| Confidence reject | Red | Empty dot | "Reject" / "0.31" |
| Status invalidated | Red | Strikethrough | "Invalidated by L1" |
| Status anomaly | Orange | Ring | "Anomaly" |
| Status HITL-pending | Yellow | Pulse | "Pending review" |
| Rank preferred | (none) | Thick stroke | "preferred" label |
| Rank deprecated | (40% opacity) | Dashed stroke | "deprecated" label |

### Text sizing + resize

- Base body 14px (small but acceptable per 2026 standards).
- Resize to 200% does not break any layout (tested by Chrome DevTools Zoom).
- No `viewport user-scalable=no`.
- Headings scale proportionally with rem units.

### Images + alt

- Lucide + Tabler icons are decorative when paired with text (`aria-hidden="true"`).
- Standalone icons (e.g., bulk-action toolbar) have `aria-label`.
- No marketing imagery in V1.5; if any added, all carry meaningful alt.
- Graph canvas: `role="application"` + `aria-label="Graph viewer — Level C analyzed graph"` + off-screen `aria-live="polite"` region for selection changes.

### Animations + flashing

- No content flashes > 3× per second (HITL pulse is 0.67 Hz; safe).
- All animations respect `prefers-reduced-motion: reduce`.
- Auto-playing video: none.

## 3. Operable

### Keyboard nav

| Element | Keys |
|---|---|
| Tab cycle | Tab / Shift+Tab through all interactive elements in document order |
| Activate | Enter on links, Space on buttons |
| Close | Esc on modals / drawers / popovers |
| Cmd-K | Open command palette globally |
| Cmd-1 / Cmd-2 / Cmd-3 | Switch graph view (Level A/B/C) when on `/graph/*` |
| J / K | Next / previous item on HITL queue pages |
| A / R / E / D | Quick-verdict on HITL pages (accept, reject, escalate, defer) |
| ? | Open keyboard shortcuts overlay |
| Sigma canvas | Tab cycles selectable nodes; Enter activates; Esc clears |
| Arrow keys | Pan graph; navigate menu items |
| +/- | Zoom graph |
| 0 | Reset graph view |

### Focus management

- Focus visible on every interactive control via `ring-2 ring-ring ring-offset-2`.
- Focus moves to modal/drawer/popover on open; returns to triggering element on close.
- Initial focus on modal: the primary action button OR the first form field.
- Skip-link in sidebar: `Skip to main content` — first focusable element.

### No keyboard traps

- Every modal / drawer / popover dismissable via Esc.
- Sigma canvas: Tab out of canvas exits canvas focus.
- Confirmation flows: Cancel button always reachable.

### Touch targets

- All interactive targets ≥ 36×36px.
- Buttons default `h-9` (36px); large variant `h-11` (44px).
- Touch-target enforcement in `01-design-system.md` §3.

### Skip links

- "Skip to main content" — first sidebar item; visible on focus.
- "Skip to filters" — on graph pages.
- "Skip to results" — on search pages.

## 4. Understandable

### Page titles

- Every page has a unique, descriptive `<title>` via Next.js metadata API.
- Pattern: `[Page] · SecBrain` (e.g., `Cluster Review · SecBrain`).

### Language

- `<html lang="en">` set in `app/layout.tsx`.
- V1.5 is English-only; V2 considers i18n.

### Form labels

- Every input has an associated `<Label>` via shadcn's `Form` primitive.
- Errors associated via `aria-describedby` to the error message.
- Required fields marked with both visible asterisk and `aria-required="true"`.

### Field validation

- Error messages plain-language:
  - "Tier L1 requires confirmation" not "Invalid tier upgrade."
  - "Connection refused — check that port 5432 is reachable" not "ECONNREFUSED."
- Validation runs on blur, not on every keystroke (less noisy).
- On submit: focus the first invalid field; announce via `aria-live="assertive"`.

### Consistent navigation

- Sidebar always visible (or collapsible to icons).
- Breadcrumbs always present on nested pages.
- TopBar always visible.
- Command palette always Cmd-K.

### Glossary tooltips

Domain terms (bitemporal, source tier, anomaly, preferred rank, signal) get a tooltip on first appearance per page explaining the concept. Tooltip is triggered by hover OR keyboard focus.

## 5. Robust

### Semantic HTML

- `<header>`, `<nav>`, `<main>`, `<footer>` landmarks used correctly.
- `<button>` for actions, `<a>` for navigation. Never `<div onClick>`.
- Headings hierarchical (`h1` → `h2` → `h3`); no skipped levels.

### ARIA used only where semantics fail

- `role="application"` for the Sigma canvas (overrides default reading; pairs with off-screen aria-live).
- `aria-live="polite"` for the global toast region + dynamic count badges + selection-change announcer.
- `aria-live="assertive"` for error alerts that need immediate attention.
- `aria-pressed` on toggle buttons (e.g., bulk-mode toggle).
- `aria-expanded` on accordion / collapsible triggers.
- `aria-selected` on tab triggers (handled by shadcn).
- `aria-current="page"` on the active sidebar item.
- `aria-busy="true"` on regions during async loading.

### Screen-reader behavior

| Screen | NVDA announces |
|---|---|
| Home | "SecBrain. Main. Heading 1: Welcome back, Mahyar. ..." |
| Cluster Review | "Cluster Review. Heading 1. 18 clusters pending. Filters region. Map / list tabs. Graph viewer application." |
| Cluster selected | "Cluster: school-selection criteria. 234 members. Verdict picker. Keep / Cull / Merge / Split / Anomaly / Defer." |
| HITL conflict | "Conflict abc123. Subject: NYU dental. Predicate: tuition resident 2024-25. Claim A: 87 thousand dollars, L1 preferred. Claim B: 40 thousand, L5 normal. System resolution: L1 wins." |

### Browser compatibility

- Chrome / Firefox / Safari current.
- No IE / Edge-Legacy support (would require polyfills).
- Tested via Playwright on Chromium + Firefox + WebKit.

## 6. Per-page accessibility budget

| Page | Concerns | Mitigation |
|---|---|---|
| Home | Lots of cards + small numbers | Each card a `<section>` with `aria-labelledby`; KPI numbers in `<dl>/<dt>/<dd>` |
| Ingestion wizard | Multi-step form | JourneyRail uses `<ol>` with each step properly marked; aria-current on active step |
| Schema mapping | Editable cells | Each cell focusable; Enter to edit; Esc to cancel; aria-label per cell |
| Cluster cull | Sigma canvas + bulk actions | Canvas application + off-screen narration; "view as table" fallback link |
| Conflict review | Side-by-side claims + verdict | `<article>` per claim; clear heading per claim; verdict radio group properly labeled |
| Level C graph | Full canvas | Canvas application + filter rail keyboard accessible + right-panel slide announced |
| PM dashboard | Multi-column with sparklines | Table semantics for the pain-point list; sparklines have visible value labels |
| Audit log | Large data table | Virtual scroll; row count announced; filter changes announced |

## 7. Common accessibility pitfalls to avoid

- ❌ Using color alone to indicate state (always color + icon + text).
- ❌ Custom focus indicators that disable browser defaults (always use `ring-*` utilities).
- ❌ Auto-focus on page load (jarring for screen readers).
- ❌ Modal that traps focus then closes by clicking outside (Esc must work).
- ❌ Toast that disappears before screen-reader announces it (use `role="status"` + 8s minimum duration).
- ❌ Drag-and-drop without keyboard alternative (provide a click-to-move dialog as fallback).
- ❌ Icons without labels in icon-only buttons (always `aria-label`).
- ❌ `<div onClick>` without role, tabindex, keyboard handler.
- ❌ Loading spinners without `aria-busy` + `aria-live` announcement.

## 8. Testing checklist (per page, before merge)

- [ ] axe-core: 0 violations.
- [ ] Lighthouse Accessibility score ≥ 95.
- [ ] Keyboard-only walkthrough: every action reachable.
- [ ] NVDA walkthrough: every page state announced sensibly.
- [ ] Tab order matches visual flow.
- [ ] Focus visible on every interactive element.
- [ ] Esc dismisses modals/drawers/popovers; focus returns to trigger.
- [ ] Reduced-motion preference simulated; animations snap or are subtler.
- [ ] Color-blindness simulation (deuteranopia + protanopia): tier signals still distinguishable.
- [ ] 200% zoom: layout doesn't break.
- [ ] No "you must allow JavaScript" interstitial; SSR renders enough content for SR to follow.

## 9. Reporting

axe-core results captured in each Playwright run. Failing tests block CI. Manual NVDA walkthrough documented in `.agent/reports/v1.5-redesign-a11y-walkthrough.md` before final sign-off.

## 10. Out of scope (V1.5)

- WCAG 2.1 AAA (V2 candidate).
- Right-to-left layout (V2 if multi-language).
- Live captions / audio descriptions (no media in V1.5).
- Cognitive-disability simplification mode (V2).
- Mobile screen-reader testing (V2).
- Sign-language interpretation (out of scope indefinitely).
