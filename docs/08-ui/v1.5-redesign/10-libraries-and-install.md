# Libraries + Install Plan

> Plug-and-play library picks, install commands, and integration order. Every library here is production-grade and battle-tested in 2025-2026 Next.js stacks.

## 0. Decision: keep the base, add the layers

**Base stack (already in V1.5 codebase, retained)**: Next.js 15, React 19, Tailwind CSS 4, TanStack Query.

**To install (in this order)**: shadcn/ui (foundation), then per-domain libraries.

## 1. Install commands (run in order)

All commands run from `web/`.

### Step 1 — shadcn primitives

```bash
cd web
pnpm dlx shadcn@latest init

# Configure:
#   Style: New York (default)
#   Base color: Zinc (will be overridden by our token system)
#   CSS variables: yes
#   Theme: write to web/src/app/globals.css
#   Components alias: @/components
#   Utils alias: @/lib/utils

# Add the 23 primitives
pnpm dlx shadcn@latest add \
  button input textarea label form select checkbox radio-group switch slider \
  dialog sheet drawer popover tooltip tabs accordion card badge avatar \
  dropdown-menu context-menu command calendar skeleton
```

### Step 2 — Theming + motion

```bash
pnpm add framer-motion next-themes tailwindcss-animate class-variance-authority
```

### Step 3 — Icons

```bash
pnpm add lucide-react @tabler/icons-react
```

### Step 4 — Graph + viz

```bash
pnpm add sigma graphology graphology-layout-forceatlas2 graphology-types
pnpm add reactflow                          # for mapping wizard drag-and-drop
pnpm add @tremor/react recharts             # charts + KPI cards
pnpm add @visx/visx                         # custom viz (sankey, sunburst, heatmap)
pnpm add d3-scale d3-array                   # visx peer deps
```

### Step 5 — UX layer

```bash
pnpm add sonner                              # toasts
pnpm add cmdk                                # command palette (shadcn integrates this)
pnpm add vaul                                # drawer (shadcn integrates this)
pnpm add react-hotkeys-hook                  # keyboard shortcuts
pnpm add @tanstack/react-table               # data table backbone
```

### Step 6 — Animated component libs

```bash
# Aceternity UI is install-by-copy; clone the components into web/src/components/animated/
# Magic UI similar
pnpm add @uiw/react-md-editor                # for refinement notes (optional, V1.6 candidate)
pnpm add embla-carousel-react                 # for trending-topic carousel
```

For Aceternity UI components: copy specific components from https://ui.aceternity.com per the per-component instructions on their site. Each component is self-contained.

For Magic UI: install via their CLI:

```bash
pnpm dlx magicui@latest add number-ticker marquee text-reveal animated-shiny-text border-beam
```

### Step 7 — Form + validation

```bash
pnpm add react-hook-form @hookform/resolvers zod
```

### Step 8 — Testing

```bash
pnpm add -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event
pnpm add -D @playwright/test @axe-core/playwright
pnpm exec playwright install chromium firefox webkit
```

### Step 9 — Dev tools

```bash
pnpm add -D @types/node @types/react @types/react-dom
pnpm add -D eslint-config-next prettier prettier-plugin-tailwindcss
```

### Step 10 — Optional (V1.6 considerations, do not install in V1.5)

- `reagraph` — 3D graph viz alternative.
- `@deck.gl/core` — only if Sigma hits scale ceiling.
- `lottie-react` — for Lottie animations in hero / onboarding.
- `@mdx-js/react` — for richer document rendering if suggested-angles grow.
- `@vercel/og` — for Open Graph image generation (V2 marketing surface).

## 2. Library responsibility matrix

| Library | Owns |
|---|---|
| **shadcn/ui** | All base UI primitives. Buttons, inputs, dialogs, etc. The 23 listed in §1 step 1. |
| **Framer Motion** | All non-CSS animations. Page transitions, modal physics, drawer slides, selection panels, sample-feed inserts. |
| **next-themes** | Dark/light mode toggle + system preference. |
| **tailwindcss-animate** | CSS keyframe animations used by shadcn (accordion expand, etc.). |
| **Lucide React** | Default icon set. Every icon unless domain-specific. |
| **Tabler Icons** | Domain-specific icons not in Lucide (DB engines, file types). |
| **Sigma + graphology** | Main graph canvas on Levels A/B/C. WebGL rendering. |
| **React Flow** | Drag-and-drop schema mapping editor. Also future: cluster-merge editor. |
| **Tremor** | KPI cards, dashboard charts (line, area, bar, donut, sparkline). |
| **Visx** | Custom data viz — sankey (tier flow), sunburst, heatmap (content gap matrix), stacked bar (tier mix). |
| **Recharts** | Fallback for tremor when we need more control over chart elements. |
| **Sonner** | Toast notifications. Better physics than shadcn's default. |
| **cmdk** | Powers shadcn's Command primitive (already integrated). |
| **Vaul** | Powers shadcn's Drawer primitive (already integrated). |
| **TanStack Query** | All data fetching + cache. |
| **TanStack Table** | All complex tables (HITL queue, audit log, source dashboards). |
| **react-hook-form + zod** | Form state + validation. |
| **react-hotkeys-hook** | Keyboard shortcuts. |
| **Aceternity UI** | Hero / empty-state illustrations + animated decorative components. |
| **Magic UI** | NumberTicker (count-up), Marquee (trending carousel), TextReveal, BorderBeam (highlight states). |
| **embla-carousel-react** | Trending-topic carousel on Social dashboard. |

## 3. Bundle-size accounting

Per-route gzipped budget target (NFR-1.5b-2: ≤ 350 KB per route):

| Route family | Libraries loaded | Estimated KB |
|---|---|---|
| Home (`/`) | shadcn + Tremor + Framer Motion + Lucide | ~85 |
| Ingest (`/ingest/*`) | + React Flow + Tabler | ~140 |
| HITL (`/hitl/*`) | + TanStack Table | ~110 |
| Graph (`/graph/*`) | + Sigma + graphology + visx | ~210 |
| Teams (`/teams/*`) | + Tremor + visx + embla | ~150 |
| Audit (`/audit`) | + TanStack Table | ~100 |
| Settings | minimal | ~70 |

All routes well under 350 KB budget. Sigma is the heaviest (~80 KB gzipped) but lazy-loaded only on `/graph/*` routes via Next.js dynamic imports.

## 4. Integration order (during the redesign implementation)

Wave 1 — Foundation (1 week):
1. Run `shadcn init` + add 23 primitives.
2. Install Framer Motion + next-themes + Lucide + Tabler.
3. Rewrite `globals.css` with the Aurora palette tokens (per `01-design-system.md` §14).
4. Build the Sidebar + TopBar + AppShell layout (per `06-hero-page-designs.md`).
5. Build shared molecules: TierBadge, ProvenancePill, TrustMeter, ConfidenceDial, EmptyState, LoadingState, ErrorState, KbShortcutsOverlay, CommandPalette, ThemeToggle, Breadcrumbs.

Wave 2 — Ingest + HITL (1.5 weeks):
1. Install React Flow.
2. Build ingest components per `07-component-vocabulary.md` §3.
3. Build HITL components per `07-component-vocabulary.md` §4.
4. Wire to existing FastAPI routes.

Wave 3 — Graph canvas (1 week):
1. Install Sigma + graphology + visx.
2. Build GraphCanvas + GraphFilters + GraphSelectionPanel + MiniMap + CitationDrawer + EntitySearch + PathFinder + LayoutPicker + LegendPanel.
3. Wire to existing 4 retrieval endpoints (per ADR-012).
4. Performance-test on 5K + 50K node fixtures.

Wave 4 — Teams (1 week):
1. Install Tremor + embla + Magic UI.
2. Build team components per `07-component-vocabulary.md` §6.
3. Wire to existing FastAPI team routes.

Wave 5 — Polish + accessibility (0.5 week):
1. Aceternity UI components for hero / empty states.
2. axe-core run; fix violations.
3. NVDA walkthrough of four primary flows.
4. Playwright suite green on Chromium + Firefox + WebKit.
5. Bundle-size verification per route.

Total: ~5 weeks of focused frontend work.

## 5. Library version pins

For reproducibility:

```json
{
  "dependencies": {
    "next": "^15.0.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "tailwindcss": "^4.0.0",
    "@tanstack/react-query": "^5.59.0",
    "@tanstack/react-table": "^8.20.0",
    "framer-motion": "^11.11.0",
    "next-themes": "^0.4.0",
    "tailwindcss-animate": "^1.0.7",
    "class-variance-authority": "^0.7.0",
    "lucide-react": "^0.460.0",
    "@tabler/icons-react": "^3.20.0",
    "sigma": "^3.0.0",
    "graphology": "^0.25.4",
    "graphology-layout-forceatlas2": "^0.10.1",
    "graphology-types": "^0.24.7",
    "reactflow": "^11.11.4",
    "@tremor/react": "^3.18.0",
    "recharts": "^2.13.0",
    "@visx/visx": "^3.12.0",
    "d3-scale": "^4.0.2",
    "d3-array": "^3.2.4",
    "sonner": "^1.7.0",
    "cmdk": "^1.0.0",
    "vaul": "^1.1.0",
    "react-hotkeys-hook": "^4.6.0",
    "embla-carousel-react": "^8.3.0",
    "react-hook-form": "^7.53.0",
    "@hookform/resolvers": "^3.9.0",
    "zod": "^3.23.0"
  },
  "devDependencies": {
    "vitest": "^2.1.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.6.0",
    "@testing-library/user-event": "^14.5.0",
    "@playwright/test": "^1.48.0",
    "@axe-core/playwright": "^4.10.0",
    "prettier": "^3.3.0",
    "prettier-plugin-tailwindcss": "^0.6.0"
  }
}
```

Use semver `^` to allow patch + minor updates within the major. Lock to exact versions only if reproducibility bugs surface.

## 6. License audit

| Library | License | OK for commercial? |
|---|---|---|
| shadcn/ui | MIT | ✅ |
| Framer Motion | MIT | ✅ |
| Lucide | ISC | ✅ |
| Tabler Icons | MIT | ✅ |
| Sigma + graphology | MIT | ✅ |
| React Flow | MIT | ✅ |
| Tremor | Apache 2.0 | ✅ |
| Visx | MIT | ✅ |
| Sonner | MIT | ✅ |
| Vaul | MIT | ✅ |
| TanStack Query + Table | MIT | ✅ |
| Aceternity UI | MIT (copy-paste, but check per-component) | ✅ |
| Magic UI | MIT | ✅ |

All permissive. V1.5 stays internal-only; V2 commercial use unaffected.

## 7. Maintenance posture

- All libraries listed are in active development as of 2026-05.
- Framer Motion → renamed to "Motion" in 2025; the API is the same; package alias `motion` is also published.
- Sigma v3 (current) is the active line; v2 deprecated.
- Tremor renamed some primitives in 2025; using current stable API.
- shadcn doesn't have versions — components are copy-paste; the registry CLI bumps as needed.

## 8. Out of scope additions

The following are NOT being added in V1.5 redesign even though they're tempting:

- **Material UI** — conflicts with shadcn philosophy.
- **Chakra UI** — overlaps shadcn.
- **Mantine** — overlaps shadcn.
- **Ant Design** — too opinionated; visual identity wrong.
- **react-spring** — Framer Motion sufficient.
- **GSAP** — overkill; Framer Motion + CSS sufficient.
- **Three.js raw** — only via Reagraph wrapper if 3D needed in V1.6.
- **D3 raw** — visx wraps it with React conventions; use visx.
- **Storybook** — V1.6 candidate; nice-to-have.
- **Chromatic** — V1.6 candidate; visual regression.

## 9. Tailwind config snippets

Add to `web/tailwind.config.ts`:

```ts
import type { Config } from 'tailwindcss';
import animate from 'tailwindcss-animate';

const config: Config = {
  darkMode: ['class'],
  content: ['./src/**/*.{ts,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        background: 'hsl(var(--background))',
        'background-warm': 'hsl(var(--background-warm))',
        surface: 'hsl(var(--surface))',
        'surface-elevated': 'hsl(var(--surface-elevated))',
        foreground: 'hsl(var(--foreground))',
        muted: 'hsl(var(--muted))',
        'muted-foreground': 'hsl(var(--muted-foreground))',
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        success: 'hsl(var(--success))',
        warning: 'hsl(var(--warning))',
        destructive: 'hsl(var(--destructive))',
        info: 'hsl(var(--info))',
        'tier-l1': { DEFAULT: 'hsl(var(--tier-l1))', bg: 'hsl(var(--tier-l1-bg))', fg: 'hsl(var(--tier-l1-fg))' },
        'tier-l2': { DEFAULT: 'hsl(var(--tier-l2))', bg: 'hsl(var(--tier-l2-bg))', fg: 'hsl(var(--tier-l2-fg))' },
        'tier-l3': { DEFAULT: 'hsl(var(--tier-l3))', bg: 'hsl(var(--tier-l3-bg))', fg: 'hsl(var(--tier-l3-fg))' },
        'tier-l4': { DEFAULT: 'hsl(var(--tier-l4))', bg: 'hsl(var(--tier-l4-bg))', fg: 'hsl(var(--tier-l4-fg))' },
        'tier-l5': { DEFAULT: 'hsl(var(--tier-l5))', bg: 'hsl(var(--tier-l5-bg))', fg: 'hsl(var(--tier-l5-fg))' },
      },
      fontFamily: {
        sans: ['Inter Variable', 'ui-sans-serif', 'system-ui'],
        mono: ['JetBrains Mono Variable', 'ui-monospace'],
      },
      keyframes: {
        'hitl-pulse': {
          '0%': { boxShadow: '0 0 0 0 hsl(var(--warning) / 0.6)' },
          '70%': { boxShadow: '0 0 0 8px hsl(var(--warning) / 0)' },
          '100%': { boxShadow: '0 0 0 0 hsl(var(--warning) / 0)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
      animation: {
        'hitl-pulse': 'hitl-pulse 1.5s ease-out infinite',
        shimmer: 'shimmer 1.5s ease-in-out infinite',
      },
    },
  },
  plugins: [animate],
};

export default config;
```

## 10. Smoke-test after install

After running all install commands:

```bash
cd web
pnpm dev                # boot Next.js; localhost:3000 loads with Aurora theme
pnpm exec tsc --noEmit  # TypeScript strict passes
pnpm lint               # ESLint passes
pnpm exec playwright test --grep "smoke"  # Smoke tests pass
```

Reports filed in `.agent/reports/v1.5-redesign-install-smoke.md`.
