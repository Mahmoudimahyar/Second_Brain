# Brand System — V1.5

> V1.5 commits to **shadcn defaults** for the brand system (V1.5-R2 user decision). No custom palette, no custom typography, no logo lockup. This doc captures what that means concretely + what's deliberately deferred to V2.

## Decision

Stay on shadcn/ui defaults for V1.5. Revisit branding in V2 when the multi-tenant reframe lands (per-tenant theming will be required then anyway).

## What V1.5 inherits from shadcn defaults

- **Color tokens**: shadcn's neutral palette + accent colors. Light/dark mode auto-toggled by system preference; user can override via `<ThemeToggle />` in top-bar.
- **Typography**: Inter (sans) + JetBrains Mono (mono) — shadcn's default pairing. Scale via Tailwind's `text-{size}` utilities.
- **Spacing**: Tailwind 4 default scale (4px base unit).
- **Borders + radius**: shadcn defaults (`--radius: 0.5rem`).
- **Shadows**: Tailwind defaults (`shadow-sm` through `shadow-2xl`).
- **Focus rings**: shadcn's accessible focus-ring (3px, accent color, 3:1 contrast).

## Project-specific deviations (minimal)

Where V1.5 needs custom semantics:

| Token | Default | V1.5 override | Why |
|---|---|---|---|
| `--tier-l1` | n/a | gold (Tailwind `amber-500`) | L1 source-tier nodes in Level C graph |
| `--tier-l2` | n/a | silver (Tailwind `slate-400`) | L2 |
| `--tier-l3` | n/a | bronze (Tailwind `orange-700`) | L3 |
| `--tier-l4` | n/a | light gray (Tailwind `gray-400`) | L4 |
| `--tier-l5` | n/a | dark gray (Tailwind `gray-700`) | L5 |
| `--status-invalidated` | n/a | red strikethrough | `invalidated_by_official_data` |
| `--status-anomaly` | n/a | orange ring | `Status='anomaly'` |
| `--status-hitl-pending` | n/a | yellow pulse | HITL-queued items |
| `--rank-preferred` | n/a | solid + thick | Wikidata `rank=preferred` |
| `--rank-normal` | n/a | thin | `rank=normal` |
| `--rank-deprecated` | n/a | dashed + faded | `rank=deprecated` |

These live in `web/src/app/globals.css` as CSS custom properties; consumed by `web/src/components/graph/*` + `ProvenancePill`.

## What's NOT in V1.5

- **Custom logo / wordmark** — none. App title "SecBrain" in the top-bar uses default font.
- **Marketing palette** — there's no marketing surface; no need.
- **Per-tenant theming** — V2 reframe.
- **Brand voice / copy guidelines** — V1 internal-only; no marketing copy. UI copy follows shadcn convention.
- **Iconography** — Lucide React (shadcn default). No custom icon set.
- **Illustrations** — none. Empty-state visuals are text + Lucide icons only.
- **Print stylesheet** — none.

## Where to override (V2 readiness)

When V2 multi-tenant lands and per-tenant theming is required, the override surface is `web/src/app/globals.css` + a per-tenant theme JSON loaded at app boot. Shadcn's CSS-custom-property design supports this cleanly. V1.5's deviation tokens above will move into the tenant-theme schema.

## Accessibility

All color overrides above meet WCAG 2.1 AA contrast on both light + dark mode backgrounds — verified by axe-core in Playwright tests per `docs/08-ui/accessibility.md`. Color is never the only signal (shape + icon doubles); see `graph-level-views.md`.

## Reuse rules (V1 scaffold rule, carried + amended)

V1's scaffold said "assets created for the website should be reusable for emails, flyers, social posts, pitch decks, ads, onboarding materials." V1.5 is internal-only — none of those surfaces exist. The reuse rule is deferred to V2 when those external surfaces appear.

## References

- shadcn/ui design tokens — https://ui.shadcn.com/themes
- V1.5-R2 user decision: "stay on shadcn defaults"
- `docs/08-ui/graph-level-views.md` — where the tier + rank + status tokens are consumed
- `docs/08-ui/accessibility.md` — contrast verification rules
