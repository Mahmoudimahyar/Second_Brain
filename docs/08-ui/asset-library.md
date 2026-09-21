# Asset Library — V1.5

> V1.5 is intentionally asset-light. No logos, no custom illustrations, no custom imagery. Icons via Lucide React (shadcn default). This doc lists what assets exist + where they live.

## Icons

- **Source**: Lucide React (shadcn-bundled).
- **Selection rule**: prefer Lucide; only add custom SVGs when Lucide has no semantically-appropriate match.
- **Custom additions in V1.5**: none. (Reconsidered in V1.6 if a domain-specific icon is unavoidable.)
- **Usage**: `<Icon className="size-4 text-muted-foreground" />` via Tailwind size utilities.
- **Sizes**: 12 / 14 / 16 / 20 / 24 px (Tailwind `size-3` / `size-3.5` / `size-4` / `size-5` / `size-6`).

## Logo / wordmark

None. App title is the literal string "SecBrain" rendered in Inter via Tailwind's text utilities. Top-bar position; semibold; default text color.

V2 candidate: introduce a logo if/when the product gets an external face.

## Illustrations / imagery

None in V1.5. Empty states use text + Lucide icons only (no Storyset / unDraw / custom drawings).

V1.6 candidate: a small set of empty-state illustrations if the product feels too sterile.

## Favicon

Default Next.js favicon (the "N" placeholder) until V1.6 decides on a brand mark. Acceptable for internal-only deployment.

## Fonts

- **Sans**: Inter via `next/font/google` (self-hosted at build time). Variable font, weight 100-900.
- **Mono**: JetBrains Mono via `next/font/google`. Variable font.
- No custom fonts in V1.5.

## Sound / video

None. V1.5 ships silent + image-free.

## Charts + data viz

- Tremor chart components (KpiCard, AreaChart, BarChart, LineChart, DonutChart, SparkArea, etc.).
- Sigma.js canvas for graph viz.
- No additional chart libs (e.g., D3 raw, Visx, recharts) — V1.5 sticks to Tremor for KPI/data viz and Sigma.js for graph.

## Where the few real assets live

```
web/
  public/
    favicon.ico             # Next.js default
    logo.svg                # (not created in V1.5)
  src/
    app/
      icon.tsx              # (Next.js dynamic icon — not used in V1.5)
      apple-icon.tsx        # (not used in V1.5)
    components/
      shared/icons/         # custom SVGs would live here — empty for V1.5
```

## Licensing

- Lucide React: ISC license. Permissive; OK for V1.5 + V2.
- Inter: SIL Open Font License. Permissive.
- JetBrains Mono: SIL OFL. Permissive.
- shadcn/ui: MIT.
- Tremor: Apache 2.0.

All assets V1.5 ships are permissively licensed for commercial use (relevant for V2 when this becomes external-facing).

## Asset rules (V1 scaffold rule, carried)

- Use consistent icon style → Lucide React enforced.
- Use consistent color tokens → Tailwind + shadcn + `brand-system.md` tokens; no hardcoded colors.
- Avoid one-off graphics unless approved → V1.5 default: no custom graphics.
- Store source files when possible → V1.5: no source assets to store.
- Document where each asset is used → tracked in this inventory.

## Inventory

| Asset | Type | File path | Usage | Notes |
|---|---|---|---|---|
| Lucide React icon set | Icon library | npm `lucide-react` | All UI icons | Default; no overrides |
| Inter (Google Font) | Typography | `next/font/google` | All UI text | Self-hosted at build time |
| JetBrains Mono | Typography | `next/font/google` | Code / monospace | Self-hosted at build time |
| Next.js default favicon | Icon | `web/public/favicon.ico` | Browser tab | Default placeholder |

## When to add an asset

Each addition writes a row in the inventory table with: name, kind (icon/illustration/logo/font), source/license, where it's used, who approved it. No silent additions.

## What's deliberately out of V1.5

- Custom logo
- Marketing imagery
- Empty-state illustrations
- Onboarding tour graphics
- Loading-animation graphics (text spinners only)
- Custom favicon
- Open Graph / Twitter Card images (no external surfaces in V1.5)
- Sound effects / notification sounds
- Video content
