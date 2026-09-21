# Design System — V1.5

> Replaces the V1 TBD scaffold. V1.5 design system = shadcn/ui + Tremor + project-specific extensions documented here.

## Foundations (inherited)

- **Primitives**: shadcn/ui — Button, Input, Form, Dialog, Drawer, Tabs, Card, DataTable, Command, Popover, Tooltip, Toast, etc. Full list in `docs/08-ui/component-inventory.md`.
- **Charts**: Tremor — KpiCard, BarChart, LineChart, AreaChart, DonutChart, SparkArea, etc.
- **Graph canvas**: Sigma.js + sigma-iv2 ForceAtlas2 worker.
- **Tokens**: Tailwind 4 + shadcn CSS custom properties + V1.5 tier/rank/status extensions per `brand-system.md`.

## Components added by V1.5

See `docs/08-ui/component-inventory.md` for the complete catalog organized by domain (Graph, Ingest, HITL, Teams, System).

## Design rules

### Composition over forking

If a shadcn primitive doesn't fit perfectly, **compose** (wrap with project-specific styling/behavior) rather than fork. Forked primitives drift from shadcn upstream and lose accessibility fixes.

Example: `CredentialField` is a composition of shadcn `Input` + an inline banner, NOT a forked Input.

### Token-first

Hardcoded colors / spacings / radii are linted out. Use Tailwind utility classes that resolve to design tokens. The tier/rank/status tokens in `brand-system.md` are the only project-specific additions.

### Single-purpose components

Every component in the inventory has one clear job. If it's tempted to handle two cases, split it.

### Accessibility by default

Every new component starts with the shadcn-equivalent accessibility primitive: correct ARIA roles, keyboard handlers, focus management. Tested via axe-core in Playwright.

### Type-safe props

Every component takes typed props (TypeScript + Zod-validated where they receive backend data). No `any`.

### Storybook (V1.6)

V1.5b ships without Storybook. V1.6 candidate: every domain component gets a Storybook entry with happy + edge-case stories.

## Naming conventions

- Components: `PascalCase` (`GraphCanvas`, `ReviewCard`)
- Files: same as component (`GraphCanvas.tsx`)
- Hooks: `useCamelCase` (`useSelectionState`)
- Prop types: `{ComponentName}Props`
- Slots: shadcn-style `{Component}.{Slot}` pattern when composing complex components

## Directory layout

```
web/src/components/
  graph/                     # GraphCanvas + filters + selection panel + citation drawer + ...
  ingest/                    # EnginePickerGrid + SchemaMappingTable + ...
  hitl/                      # ReviewCard + per-type bodies + verdict picker + ...
  team/                      # PainPointTable + ... + TeamDashboardLayout
  shared/                    # Sidebar + TopBar + CommandPalette + EmptyState + ...
  ui/                        # shadcn-generated primitives (project-tweaked theme only)
```

## Colors

Defaults from shadcn + project tokens per `brand-system.md`. Light + dark mode supported via the standard shadcn `data-theme` mechanism.

## Typography

Inter (sans) + JetBrains Mono (mono) via Next.js `next/font/google`. Tailwind utility scale.

## Spacing

Tailwind 4 default 4px base unit. Standard utility classes (`p-1` / `p-2` / `p-4` / etc.).

## When to add a new component

- Repeats in ≥ 2 places.
- Has clear single purpose.
- Composed from primitives.
- Tested (Vitest unit; Playwright E2E if it has interaction).

## When NOT to add a new component

- One-off use cases — inline JSX is fine.
- Wraps a primitive only to add styling — use Tailwind classes inline.
- Couples view + business logic (lift the logic to a hook).

## Accessibility

Every component meets WCAG 2.1 AA per `docs/08-ui/accessibility.md`. Verified by axe-core in Playwright.

## References

- [shadcn/ui docs](https://ui.shadcn.com/)
- [Tremor docs](https://www.tremor.so/docs)
- `docs/08-ui/component-inventory.md` (catalogue)
- `docs/08-ui/brand-system.md` (tokens)
- `docs/08-ui/accessibility.md` (a11y rules)
