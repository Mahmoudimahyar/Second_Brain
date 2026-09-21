# Design System v2 — Aurora

> Replaces the V1.5 "shadcn defaults" decision in `docs/08-ui/brand-system.md`. The redesign brand is **Aurora** — deep indigo core, amber for canonical truth, semantic tier colors for the L1–L5 trust schema, dark mode by default. Per `/design:design-system`.

## 0. Why Aurora

SecBrain ingests heterogeneous data and resolves it to canonical truth. The visual identity needs to communicate three ideas:

1. **Depth** — we go many layers deep (raw → structural → clusters → analyzed → verified). Color should layer.
2. **Authority** — when something is L1 ground truth, it should *feel* gold-stamped. Not "another row in a table."
3. **Calm intelligence** — the user is in flow state reviewing decisions. The UI should not shout. Most pixels are neutral; accent appears only where it earns the eye.

Aurora is the visual answer: a near-black foundation, deep indigo as the resting primary, and an amber + tier-color palette that only shows up on meaningful surfaces.

## 1. Color tokens

All colors are defined as CSS custom properties in `web/src/app/globals.css`. shadcn-compatible — works with shadcn's CSS-variable theming.

### Neutral foundation (both modes)

```css
/* Light mode */
--background:        0 0% 100%;        /* #FFFFFF — pure white */
--background-warm:   60 33% 98%;       /* #FAFAF7 — subtle warm tint, used for content regions */
--surface:           60 14% 96%;       /* #F5F5F2 — cards / panels */
--surface-elevated:  0 0% 100%;        /* white with shadow */
--foreground:        240 6% 10%;       /* #18181B — near black */
--muted:             240 5% 64%;       /* #94959B */
--muted-foreground:  240 4% 46%;       /* #71717A */
--border:            240 6% 90%;       /* #E4E4E7 */
--input:             240 6% 90%;
--ring:              239 84% 67%;      /* indigo focus ring */

/* Dark mode (default for power users) */
--background:        240 10% 4%;       /* #0A0A0B — near-black */
--background-warm:   240 8% 7%;        /* #121215 */
--surface:           240 6% 10%;       /* #18181B */
--surface-elevated:  240 5% 13%;       /* #1F1F23 */
--foreground:        0 0% 98%;         /* #FAFAFA */
--muted:             240 4% 46%;       /* #71717A */
--muted-foreground:  240 5% 65%;       /* #A1A1AA */
--border:            240 4% 16%;       /* #27272A */
--input:             240 4% 16%;
--ring:              239 84% 67%;
```

### Brand colors

```css
--primary:           239 84% 67%;      /* #6366F1 — Indigo 500/Mid */
--primary-dim:       234 89% 74%;      /* #818CF8 — softer, used in dark mode */
--primary-foreground: 0 0% 100%;       /* always white text on primary surfaces */

--accent:            38 92% 50%;       /* #F59E0B — Amber 500 (L1 truth + key CTAs) */
--accent-foreground: 26 83% 14%;       /* dark warm for text on amber */

/* Semantic states */
--success:           158 64% 52%;      /* #10B981 — Emerald 500 */
--warning:           38 92% 50%;       /* #F59E0B — same as accent (intentional) */
--destructive:       0 84% 60%;        /* #EF4444 — Red 500 */
--info:              199 89% 48%;      /* #0EA5E9 — Sky 500 */
```

### Tier colors (L1–L5 — required for graph + provenance pills)

These are domain-specific and must be applied wherever a `source_tier` appears.

```css
--tier-l1:           38 92% 50%;       /* #F59E0B — Amber (canonical truth) */
--tier-l1-bg:        38 92% 95%;       /* light wash for chip background */
--tier-l1-fg:        26 83% 14%;       /* dark warm text */

--tier-l2:           177 70% 41%;      /* #14B8A6 — Teal (verified secondary) */
--tier-l2-bg:        177 70% 96%;
--tier-l2-fg:        177 70% 18%;

--tier-l3:           262 83% 58%;      /* #8B5CF6 — Violet (curated community) */
--tier-l3-bg:        262 83% 96%;
--tier-l3-fg:        262 83% 25%;

--tier-l4:           240 5% 50%;       /* #71717A — Zinc (raw web) */
--tier-l4-bg:        240 5% 95%;
--tier-l4-fg:        240 5% 25%;

--tier-l5:           340 75% 55%;      /* #E11D48 — Rose (forum / social) */
--tier-l5-bg:        340 75% 96%;
--tier-l5-fg:        340 75% 25%;
```

### Rank styling (Wikidata schema)

Applied to edges + claim emphasis:

| Rank | Visual treatment |
|---|---|
| `preferred` | Solid stroke; 1.5× width; opacity 100% |
| `normal` | Solid stroke; 1× width; opacity 90% |
| `deprecated` | Dashed stroke; 1× width; opacity 40%; muted color |

### Status overlays

| Status | Visual |
|---|---|
| `invalidated_by_official_data` | Red strikethrough on text; thin red border (`hsl(var(--destructive))`) |
| `anomaly` | Orange ring (2px outline, `hsl(38 92% 60%)`) around the node |
| `hitl_pending` | Yellow pulse — `box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.7)` animated to `0 0 0 8px transparent` over 1.5s, loops |
| `superseded` | 60% opacity + small clock icon |
| `committed` | Subtle green dot in top-right corner |

### Confidence colors

For confidence-band UI (HITL routing):

| Confidence | Color | Use |
|---|---|---|
| `≥ 0.90` | success (emerald) | Auto-accept routing chip |
| `0.75–0.90` | warning (amber) | HITL routing chip |
| `< 0.75` | destructive (red) | Reject routing chip |
| Unknown | muted (zinc) | "No confidence calculated" |

## 2. Typography

### Font stack

```css
font-sans: 'Inter Variable', ui-sans-serif, system-ui, sans-serif;
font-mono: 'JetBrains Mono Variable', ui-monospace, 'SF Mono', monospace;
```

Both loaded via `next/font/google` with `display: swap`. Variable fonts so the entire weight range is available without extra HTTP.

### Type scale

| Token | Size / Line-height | Weight | Tracking | Use |
|---|---|---|---|---|
| `display-1` | 48px / 56px | 600 | -0.025em | Hero blocks, empty-state headlines |
| `display-2` | 36px / 44px | 600 | -0.02em | Section banners |
| `h1` | 30px / 36px | 600 | -0.015em | Page title |
| `h2` | 24px / 32px | 600 | -0.01em | Section header |
| `h3` | 20px / 28px | 600 | 0 | Card / panel title |
| `h4` | 18px / 24px | 500 | 0 | Subsection |
| `body-lg` | 16px / 24px | 400 | 0 | Lead text, important body |
| `body` | 14px / 20px | 400 | 0 | Default body |
| `body-sm` | 13px / 18px | 400 | 0.005em | Secondary body |
| `caption` | 12px / 16px | 500 | 0.02em | Labels, meta, chips |
| `overline` | 11px / 14px | 600 | 0.08em (uppercase) | Section eyebrows |
| `mono` | 13px / 18px | 400 | 0 | IDs, hashes, code |
| `mono-sm` | 11px / 14px | 400 | 0 | Inline references |

Tailwind utilities follow Tailwind's standard scale (`text-sm`, `text-base`, etc.); the table above maps each to a custom utility in `@layer base`.

### Weight usage

- 400 (Regular) — default body
- 500 (Medium) — secondary headings, labels, button text
- 600 (Semibold) — primary headings, page titles, important CTAs
- 700 (Bold) — sparingly; only when 600 + size isn't enough

Never use 900 (Black) — too heavy for an analytical UI.

### Line-height + letter-spacing rules

- Headings: tighter (tracking-tight = -0.015em).
- Body: default (0).
- Captions / overlines: looser (tracking-wider = 0.02-0.08em).
- Mono: always 0 tracking; line-height ≥ 1.4 for code blocks.

### Numerals

Tabular nums for any number that aligns vertically in tables / dashboards:
```css
font-variant-numeric: tabular-nums;
```
Default in `<td>`, `<dd>`, `.metric-value`, `.kpi-card-number`.

## 3. Spacing system

4px base. Use Tailwind's default scale (`p-1` = 4px, `p-2` = 8px, ..., `p-8` = 32px).

### Vertical rhythm

| Level | Tailwind | Use |
|---|---|---|
| Tight inline | `space-x-1` (4px) | Icon + chip text |
| Tight stack | `space-y-1.5` (6px) | Form-field label + input |
| Default stack | `space-y-3` (12px) | Card body items |
| Section stack | `space-y-6` (24px) | Sub-sections within a page |
| Page sections | `space-y-10` (40px) | Major page section breaks |

### Container

- Outer page padding: `p-6` (24px) on the `<main>`.
- Card padding: `p-4` (16px) for compact, `p-6` (24px) for primary content.
- Drawer / Sheet padding: `p-6`.
- Modal padding: `p-6` body, `p-4` header/footer.
- Toast: `px-4 py-3`.

### Touch targets

Even on desktop, interactive elements ≥ 36×36px. Nav items become `h-10` (40px) with icon + label. Buttons default `h-9` (36px); compact `h-8` (32px); large `h-11` (44px).

## 4. Elevation + surface

shadcn-style 4-tier surface model:

| Tier | Use | Light mode | Dark mode |
|---|---|---|---|
| **Page** | Outer body | `bg-background` | `bg-background` |
| **Container** | Content region within page | `bg-background-warm` | `bg-background-warm` |
| **Card** | Resting card / panel | `bg-surface` border `border` | `bg-surface` border `border` |
| **Elevated** | Modal, dropdown, popover, drawer | `bg-surface-elevated` shadow-lg | `bg-surface-elevated` shadow-lg |

Shadow tokens:

```css
--shadow-sm: 0 1px 2px hsl(240 4% 0% / 0.05);
--shadow:    0 1px 3px hsl(240 4% 0% / 0.08), 0 1px 2px hsl(240 4% 0% / 0.04);
--shadow-md: 0 4px 6px hsl(240 4% 0% / 0.06), 0 2px 4px hsl(240 4% 0% / 0.04);
--shadow-lg: 0 10px 15px hsl(240 4% 0% / 0.08), 0 4px 6px hsl(240 4% 0% / 0.04);
--shadow-xl: 0 20px 25px hsl(240 4% 0% / 0.10), 0 8px 10px hsl(240 4% 0% / 0.04);

/* Dark mode shadows are stronger (the background is dark; shadow can be denser) */
.dark {
  --shadow-sm: 0 1px 2px hsl(0 0% 0% / 0.4);
  --shadow:    0 1px 3px hsl(0 0% 0% / 0.5), 0 1px 2px hsl(0 0% 0% / 0.4);
  --shadow-md: 0 4px 6px hsl(0 0% 0% / 0.5), 0 2px 4px hsl(0 0% 0% / 0.4);
  --shadow-lg: 0 10px 15px hsl(0 0% 0% / 0.6), 0 4px 6px hsl(0 0% 0% / 0.4);
  --shadow-xl: 0 20px 25px hsl(0 0% 0% / 0.7), 0 8px 10px hsl(0 0% 0% / 0.5);
}
```

## 5. Border radius

| Token | Value | Use |
|---|---|---|
| `rounded-sm` | 4px | Chips, small badges |
| `rounded` | 6px | Inputs, default cards |
| `rounded-md` | 8px | Buttons, secondary cards |
| `rounded-lg` | 12px | Primary cards, modal corners |
| `rounded-xl` | 16px | Hero blocks, image masks |
| `rounded-full` | 9999px | Avatars, dots, status indicators |

## 6. Motion language (summary; full spec in `08-motion-language.md`)

### Principles

1. **Purposeful** — every motion explains a state change.
2. **Calm** — never bouncy, never excessive. Spring physics tuned to "confident."
3. **Respectful** — `prefers-reduced-motion` snaps to final state.
4. **Performant** — only `transform` + `opacity`. No `width`/`height` animation.

### Easing curves

```css
--ease-out:   cubic-bezier(0.16, 1, 0.3, 1);     /* default for content arrivals */
--ease-in-out: cubic-bezier(0.4, 0, 0.2, 1);     /* default for layout shifts */
--ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1); /* very subtle bounce — only for emphasis */
```

### Duration tokens

| Token | ms | Use |
|---|---|---|
| `duration-fast` | 100 | Hover, focus, tap |
| `duration-default` | 150 | Color change, opacity, small transforms |
| `duration-medium` | 200 | Content swap, drawer slide |
| `duration-slow` | 300 | Page transition, modal entry |
| `duration-deliberate` | 400 | Hero animation, first-load reveal |

Anything > 400ms requires explicit justification in the component spec.

### Standard transitions

- **Hover**: `transition-colors duration-default` on bg + border + text.
- **Focus**: `ring-2 ring-ring ring-offset-2` instant.
- **Page enter**: Framer Motion `<motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, ease: 'easeOut' }}>`.
- **Modal enter**: scale 0.96 → 1, opacity 0 → 1, 200ms ease-out.
- **Drawer slide**: x from 100% → 0, 250ms ease-out (Vaul handles this).
- **Toast enter**: y from 24 → 0, opacity 0 → 1, spring physics.
- **Graph node selected**: scale 1 → 1.15 → 1.1 (settle), 300ms spring.
- **Number count-up** (KPI cards): 800ms ease-out from 0 → target, only on initial mount.

## 7. Iconography

### Primary library: **Lucide React**

- 1000+ icons, MIT licensed.
- Stroke-based, consistent 2px stroke, 24×24 viewport.
- Default size in components: 16×16 (`size-4`) or 20×20 (`size-5`).
- Default stroke width: 2 (slightly tighter than Lucide default for the small sizes).

### Secondary library: **Tabler Icons React**

For domain-specific icons Lucide doesn't have:
- Database engines (Postgres, MySQL, Neo4j, SQLite)
- File types (Excel, PDF, JSONL)
- Scientific / lab-domain visuals

Use Tabler ONLY when Lucide is insufficient. Track exceptions in `docs/08-ui/asset-library.md`.

### Icon usage rules

- Always paired with text in nav (icon + label, not icon-only).
- Icon-only is allowed in compact toolbars + bulk-action toolbar + close buttons; ALWAYS with `aria-label`.
- Color inherits from text by default. Tint icon explicitly only when communicating semantic state (e.g., success green, warning amber).
- Size matches text height: `size-4` next to `body` text, `size-5` next to `body-lg`, `size-6` next to `h3+`.

## 8. Recommended libraries

### Plug-and-play (install + use)

| Library | Why | Where |
|---|---|---|
| **shadcn/ui** | Base primitive layer | `web/src/components/ui/*` — run `shadcn init` then add the 18 primitives in `07-component-vocabulary.md` |
| **Aceternity UI** | Stunning animated hero components | Home page hero, empty-state illustrations |
| **Magic UI** | Animated shadcn components (numbers ticking, card stacks, marquees) | KPI dashboards, team dashboards |
| **Framer Motion** | Animation primitives | Page transitions, drawer slides, graph selection |
| **Sigma.js** + **graphology** + **graphology-layout-forceatlas2** | WebGL graph canvas | `/graph/{structural,clusters,analyzed}` |
| **React Flow** | Drag-and-drop node editor | Mapping wizard, future cluster-merge tool |
| **Tremor** | KPI / dashboard charts | Home dashboard, team dashboards, audit page |
| **Recharts** or **visx** | Custom viz (radar, sunburst) | Trust-tier breakdown widget, cluster sentiment heatmap |
| **Lucide React** | Default icons | Everywhere |
| **Tabler Icons React** | Domain-specific icons (DBs, files) | Engine pickers, file types |
| **Sonner** | Better toasts than shadcn default | Globally |
| **cmdk** | Command palette (Cmd-K) | Top bar global search |
| **vaul** | Drawer / sheet primitive | Citation drawer, mobile-friendly settings |
| **@tanstack/react-query** | Data fetching + cache | Already in stack |
| **@tanstack/react-table** | Headless table for HITL queue + audit | `/audit`, `/hitl/history`, source dashboards |
| **react-hotkeys-hook** | Keyboard shortcuts | Every review page |
| **next-themes** | Dark/light mode toggle | Globally |
| **zod** | Schema validation | API client + forms |
| **@hookform/resolvers** + **react-hook-form** | Form state | All forms |

### Optional / experimental

- **Reagraph** — React-native 3D graph viz; consider for V1.6 graph drill-down.
- **deck.gl** — only if Sigma.js hits scale ceiling on a real corpus.
- **mdx-remote** — for the suggested-angles drafts if they grow into markdown documents.

### Do NOT add

- **Material UI**, **Ant Design** — conflicts with shadcn aesthetic.
- **Three.js raw** — only via Reagraph wrapper if 3D needed.
- **D3 directly** — visx wraps D3 with React conventions; use visx.
- **Bootstrap** — obviously.

## 9. Dark mode is the default

V1.5 ships with dark mode as default. Reasoning:
- Users are reviewing large amounts of data in long sessions — dark mode reduces eye fatigue.
- The Aurora palette is designed dark-first.
- Light mode is fully supported and toggled by the user; system preference respected.

`next-themes` controls the toggle. The `<ThemeToggle />` lives in the top-right of `TopBar`.

## 10. Layout primitives

### App shell

```
┌────────────────────────────────────────────────────────────┐
│ ┌─────────┐ ┌──────────────────────────────────────────┐ │
│ │         │ │ TopBar (h-14): corpus / time / as-of /   │ │
│ │ Sidebar │ │   search / theme-toggle / cmd-k hint     │ │
│ │ (w-60)  │ ├──────────────────────────────────────────┤ │
│ │         │ │                                          │ │
│ │  Brand  │ │              <main>                      │ │
│ │  glyph  │ │           (p-6, max-w-7xl                │ │
│ │  +      │ │            on dashboards;                │ │
│ │  Sec-   │ │            full-width on graph)         │ │
│ │  Brain  │ │                                          │ │
│ │         │ │                                          │ │
│ │  Nav    │ │                                          │ │
│ │  ─────  │ │                                          │ │
│ │  ◉ Home │ │                                          │ │
│ │  ⇨ Ingest│ │                                          │ │
│ │  ✓ HITL │ │                                          │ │
│ │  ◯ Graph│ │                                          │ │
│ │  ◇ Teams│ │                                          │ │
│ │  ⏱ Audit│ │                                          │ │
│ │  ⚙ Set  │ │                                          │ │
│ │         │ │                                          │ │
│ └─────────┘ └──────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────┘
```

- Sidebar fixed at `w-60` (240px) on `xl` screens, collapsible to `w-16` (64px, icons-only) on toggle.
- TopBar fixed `h-14` (56px) with sticky positioning.
- Main content area scrolls independently with `overflow-y-auto`.

### Page templates

Three reusable layouts:

1. **Dashboard** — `max-w-7xl mx-auto`, multi-column grid, KPI cards on top, lists below.
2. **Detail / Form** — `max-w-3xl mx-auto`, single column, breadcrumbs above title.
3. **Graph** — full-width, no max-width, sidebar collapsible to give canvas more space.

### Responsive

- Sidebar collapses to a Sheet-style drawer on `< lg` (1024px).
- Tables become Card lists on `< md` (768px).
- Graph canvas hides MiniMap on `< xl`.
- All forms become single-column on `< md`.

## 11. Empty / loading / error states

Every page state has a defined treatment:

### Empty state pattern

```tsx
<EmptyState
  icon={<DatabaseZap className="size-12 text-muted-foreground" />}
  title="No sources connected yet"
  description="Connect a database, upload a file, or run a forum dump to get started."
  primaryAction={{ label: "Connect a source", href: "/ingest/new" }}
  secondaryAction={{ label: "Read the docs", href: "/docs" }}
/>
```

### Loading state pattern

Skeletons matching the final layout (shadcn `<Skeleton />`). NOT spinners on full-page loads — they fail to communicate what's loading.

Use a spinner ONLY for actions inside an interactive element (button while saving).

### Error state pattern

```tsx
<ErrorState
  title="We couldn't load your data"
  description="The graph store didn't respond. Try again, or check your audit log for details."
  primaryAction={{ label: "Retry", onClick: refetch }}
  secondaryAction={{ label: "View audit log", href: "/audit" }}
  technical={error.message}  // collapsible drawer
/>
```

## 12. The 18 shadcn primitives we'll actually install

Run `pnpm dlx shadcn@latest init` then `pnpm dlx shadcn@latest add` each:

1. Button
2. Input
3. Textarea
4. Form (+ Label + Form*)
5. Select
6. Checkbox
7. Radio Group
8. Switch
9. Slider
10. Dialog
11. Sheet (Drawer)
12. Popover
13. Tooltip
14. Tabs
15. Accordion
16. Card
17. Badge
18. Avatar
19. DropdownMenu
20. ContextMenu
21. Command (Cmd-K palette)
22. Calendar
23. Skeleton

That's 23 actually. Plus DataTable (built on Tanstack Table, doc'd separately).

## 13. What's the budget for this design system?

**Total time to apply across the V1.5 implementation**: ~3 weeks of focused frontend work. Breakdown in `09-implementation-plan.md` (TBD).

**Total bundle size impact**:
- shadcn primitives: ~25 KB gzipped (each is ~1-2 KB; tree-shakeable).
- Framer Motion: ~30 KB gzipped.
- Sigma.js + graphology: ~80 KB gzipped (lazy-loaded only on `/graph/*`).
- Tremor: ~40 KB gzipped (lazy-loaded only on dashboards).
- Lucide + Tabler: ~5 KB gzipped (per-icon tree-shaken).
- Sonner: ~3 KB gzipped.
- Total initial JS: well under the 350 KB / route budget from V1.5b NFR-2.

## 14. Theme tokens — final form

Combining all of the above, here's the `globals.css` skeleton:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    /* Surfaces */
    --background: 0 0% 100%;
    --background-warm: 60 33% 98%;
    --surface: 60 14% 96%;
    --surface-elevated: 0 0% 100%;
    --foreground: 240 6% 10%;
    --muted: 240 5% 64%;
    --muted-foreground: 240 4% 46%;
    --border: 240 6% 90%;
    --input: 240 6% 90%;
    --ring: 239 84% 67%;

    /* Brand */
    --primary: 239 84% 67%;
    --primary-foreground: 0 0% 100%;
    --accent: 38 92% 50%;
    --accent-foreground: 26 83% 14%;

    /* States */
    --success: 158 64% 52%;
    --warning: 38 92% 50%;
    --destructive: 0 84% 60%;
    --info: 199 89% 48%;

    /* Tiers */
    --tier-l1: 38 92% 50%;
    --tier-l1-bg: 38 92% 95%;
    --tier-l1-fg: 26 83% 14%;
    --tier-l2: 177 70% 41%;
    --tier-l2-bg: 177 70% 96%;
    --tier-l2-fg: 177 70% 18%;
    --tier-l3: 262 83% 58%;
    --tier-l3-bg: 262 83% 96%;
    --tier-l3-fg: 262 83% 25%;
    --tier-l4: 240 5% 50%;
    --tier-l4-bg: 240 5% 95%;
    --tier-l4-fg: 240 5% 25%;
    --tier-l5: 340 75% 55%;
    --tier-l5-bg: 340 75% 96%;
    --tier-l5-fg: 340 75% 25%;

    /* Radius */
    --radius: 0.5rem;
  }

  .dark {
    --background: 240 10% 4%;
    --background-warm: 240 8% 7%;
    --surface: 240 6% 10%;
    --surface-elevated: 240 5% 13%;
    --foreground: 0 0% 98%;
    --muted: 240 4% 46%;
    --muted-foreground: 240 5% 65%;
    --border: 240 4% 16%;
    --input: 240 4% 16%;
    --ring: 239 84% 67%;
    --primary: 234 89% 74%;
    /* Brand tokens stay; surfaces invert. Tier backgrounds in dark: lower lightness. */
    --tier-l1-bg: 38 92% 12%;
    --tier-l2-bg: 177 70% 12%;
    --tier-l3-bg: 262 83% 14%;
    --tier-l4-bg: 240 5% 18%;
    --tier-l5-bg: 340 75% 14%;
  }

  /* Always-on */
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
      animation-duration: 0.01ms !important;
      animation-iteration-count: 1 !important;
      transition-duration: 0.01ms !important;
      scroll-behavior: auto !important;
    }
  }
}
```

Continued in `02-data-source-journeys.md` (per-source UX), `03-graph-visualization.md` (graph canvas), `04-processing-states.md`, `05-trust-tier-ux.md`, `06-hero-page-designs.md`, `07-component-vocabulary.md`, `08-motion-language.md`, `09-accessibility.md`.
