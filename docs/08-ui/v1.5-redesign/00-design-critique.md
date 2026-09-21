# Design Critique — V1.5 Implementation (as of 2026-05-25)

> Per `/design:design-critique`. Critique of the V1.5 web UI as shipped by the prior implementation session. The findings here drive the redesign documents that follow.

## Overall impression

**The UI looks unbuilt.** Not "minimal" — unbuilt. Three signals:
- `web/src/components/ui/` is empty — `shadcn init` was never run, so the standardized primitives don't exist. Pages inline `<input className="rounded border border-gray-300 px-3 py-1.5 text-sm">` directly.
- No icons anywhere. Lucide is in the package surface but the sidebar is a column of unstyled text links. The top bar shows `"V1.5 localhost · single-user · no auth"` as the only chrome.
- No color identity. `globals.css` is HSL neutrals only. Every border is `border-gray-200`. Tier semantics (L1 gold, L2 silver, etc.) specified in `brand-system.md` were not applied to any element.

It reads as a backend developer's debug surface that someone forgot to skin. There is no first-look "this is a knowledge engine" identity, no hierarchy beyond `text-2xl` for headings and `text-sm text-gray-500` for everything else, no motion, no spatial rhythm.

## Usability

| Finding | Severity | Recommendation |
|---|---|---|
| Sidebar nav has 7 text links with no icons, no grouping, no section headers, no active-state polish beyond `bg-gray-200`. Hard to scan; harder still in a glance. | 🔴 Critical | Build a proper nav (icons + section grouping + collapsed/expanded states + active indicator bar). |
| Top bar shows static strings instead of the corpus picker, time-range picker, as-of picker, and search per spec `docs/08-ui/site-map.md`. The most important global controls are absent. | 🔴 Critical | Implement the spec'd TopBar with the four global controls + theme toggle. |
| Home page is a 6-card grid with `text-xs` descriptions and no visual differentiation between sections. A user lands here and gets zero situational awareness — no "what's pending in HITL", no "what was last ingested", no "graph stats". | 🔴 Critical | Redesign Home as a dashboard: corpus health card, HITL inbox counts, recent activity, graph state at-a-glance, top open questions. |
| The three graph routes (`/graph/structural`, `/graph/clusters`, `/graph/analyzed`) show a search input + result list only. No graph visualization. The visual centerpiece of V1.5 is missing entirely. | 🔴 Critical | Implement the Sigma.js canvas per `docs/08-ui/graph-level-views.md` + this redesign's `03-graph-visualization.md`. |
| Empty states are absent. "No results found" is the closest the app gets. Empty `/hitl` says nothing about what HITL is, what to do next, or why the inbox is empty. | 🔴 Critical | Empty states with illustration + 1-sentence purpose + primary CTA per `04-processing-states.md`. |
| Forms have no validation feedback beyond browser-default error popups. A failed Postgres connection probably surfaces as `{"detail": "connection refused"}` JSON in a toast. | 🟡 Moderate | Inline field validation + structured error envelope rendering. |
| No keyboard shortcuts surface. Spec listed Cmd-K + Cmd-1/2/3 + J/K/A/R/E/D — none implemented. | 🟡 Moderate | Wire shortcuts + a `?` overlay listing them per page. |
| No undo. HITL commit toast shows for ~2 seconds with no rollback path. | 🟡 Moderate | Sonner toast with 5s undo timer per `docs/08-ui/hitl-flows.md`. |
| The audit log page filters are uncertain because they're not actually wired — the spec calls for kind / actor / time-range / source filters; the implementation has none. | 🟡 Moderate | Wire all four filters as described in `02-data-source-journeys.md` + per-page IA. |
| No drag-to-reorder, no drag-to-merge, no inline editing. Every interaction is a click → modal → confirm. The mapping wizard especially needs richer interaction. | 🟢 Minor (V1.6) | React Flow for the mapping wizard's drag-and-drop schema mapping. |

## Visual hierarchy

- **What draws the eye first**: nothing in particular. The page header (`text-3xl font-semibold` with `text-sm text-gray-500` description) is the tallest text but blends into the rest of the gray.
- **Reading flow**: undirected. There's no eye-leading composition — no hero block, no primary CTA, no progressive disclosure. Cards are equal-weight 1-of-6 in a flat grid.
- **Emphasis**: nothing emphasized. Tailwind's `font-semibold` + `text-gray-500` is the entire weight system. No accent color, no surface elevation, no visible interactive state beyond a 100ms hover.

**Recommendation**: introduce a 4-step visual hierarchy:
1. **Identity** — top-left brand mark (currently text "SecBrain", needs a glyph).
2. **Context** — top bar with corpus + time + search.
3. **Primary action** — page-level CTA in accent color (e.g., "Pull now" on connector dashboard).
4. **Content** — the actual data, with body color hierarchy (default / muted / subtle).

## Consistency

| Element | Issue | Recommendation |
|---|---|---|
| Borders | All `border-gray-200`, regardless of context. No layered surface model. | Adopt shadcn's `--border` token + surface elevation (border / muted / subtle / hover). |
| Spacing | `space-y-4` / `space-y-6` used arbitrarily. No spacing rhythm. | Adopt a vertical-rhythm scale: 4/8/12/16/24/32/48 with documented use cases. |
| Typography | Two sizes (text-2xl + text-sm) covers ~90% of text. No display, no caption, no mono. | Adopt the type scale in `01-design-system.md`. |
| Color | No accent. No tier semantics applied. No success/warning/destructive. | Adopt the Aurora palette in `01-design-system.md`. |
| Icons | None used. | Adopt Lucide + Tabler combo per `01-design-system.md` libraries section. |
| Motion | None. Hover is the only transition, applied via Tailwind's default 150ms. | Adopt Framer Motion + the motion language in `01-design-system.md` motion section. |

## Accessibility

| Check | Pass / Fail | Notes |
|---|---|---|
| Skip-link present | ✅ pass | Sidebar has `Skip to main content` correctly. |
| Color contrast 4.5:1 on body text | ✅ likely pass | `text-gray-500 on white` is borderline ~4.6:1; `text-gray-400` (used on the top bar) fails at ~3.3:1. |
| Touch target ≥ 44×44 | 🟡 borderline | Sidebar links are `px-2 py-1 text-sm` — ~24px tall. Below the touch threshold even though V1.5 is desktop. |
| Focus visible | 🟡 only default browser ring | shadcn's stronger focus-ring isn't applied because shadcn isn't installed. |
| Reduced motion respected | ✅ pass | `@media (prefers-reduced-motion: reduce)` block in `globals.css` disables animation. |
| Screen-reader landmarks | 🟡 partial | `<nav aria-label="Primary">` is set; `<main id="main">` is set. Missing `<header>` semantics on TopBar (it's wrapped in plain `<header>` so this one's actually fine). |
| axe-core 0 violations | ❌ never run | per gap audit; CI gate not invoked. |
| Keyboard nav for Sigma canvas | N/A | canvas doesn't exist yet. |

**Recommendation**: when the canvas + components land, build with axe-core as part of the Playwright suite. Block PRs on violations.

## What works well (the small list)

- The Next.js + FastAPI architecture choice is sound. Won't need re-platforming.
- The 25 page routes are scaffolded and reachable, so the IA is at least confirmed.
- Reduced-motion handling is correctly wired at the CSS level.
- Skip-link is properly implemented.
- The sidebar's active-state detection logic (`pathname === item.href || pathname.startsWith(item.href + "/")`) is correct.
- Localhost-only binding (`127.0.0.1`) is honored per V1.5-R1.

That's about it. The structural decisions were right; the visual + interaction polish is missing.

## Priority recommendations

1. **Run `shadcn init` properly**. The current state is "Tailwind + nothing." Adding the shadcn primitives (Button, Input, Card, Dialog, DropdownMenu, Form, Toast, Tooltip, Skeleton, DataTable, Command, Sheet, Tabs, Avatar) is the single highest-impact change. Most of the visual gap is "buttons look like buttons" territory.
2. **Adopt the Aurora palette** (`01-design-system.md`). Pick three colors and apply them everywhere: indigo primary, amber accent, neutral surfaces with tier-specific gold/cyan/violet/gray/rose for the L1–L5 schema. Without this, the app reads as "incomplete." With it, the app reads as "intentional."
3. **Build the Sigma.js canvas**. The graph viewer is the visual centerpiece. A force-directed canvas with proper styling makes V1.5 look like a knowledge engine instead of a database CRUD app. Spec in `03-graph-visualization.md`.
4. **Redesign the Home page as a dashboard**. Currently a card grid. Should be: corpus health + HITL inbox + recent activity + graph stats + top open questions + quick actions. Spec in `06-hero-page-designs.md`.
5. **Implement motion**. Framer Motion on page transitions, card hovers, drawer slides, graph node selection, toast undo. Spec in `08-motion-language.md`. Without motion the app feels static; with it, modern.
6. **Build the proper component vocabulary**. Per `07-component-vocabulary.md`: ProvenancePill, TierBadge, TrustMeter, ConfidenceDial, ClusterCard, ProposalCard, etc. These are the V1.5-specific molecules that the V1.5 work was supposed to ship.

The rest of this design package details each of these.

## Stage-appropriate context

This critique is for content in the **post-spec, pre-redesign-implementation** stage. The implementation exists; it's just visually un-finished. Feedback is calibrated accordingly:
- Not blocking architecture (FastAPI / Next.js / shadcn / Sigma.js stack is right).
- Not blocking IA (the 25 routes + 60 components catalog are correct).
- Blocking the actual look-and-feel + interaction layer + visual identity.
