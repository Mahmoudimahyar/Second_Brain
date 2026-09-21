# Motion Language

> Full motion spec. Framer Motion + CSS transitions. The rules in `01-design-system.md` §6 are the headline; this doc is the detailed implementation.

## 0. Three principles

1. **Purposeful** — every motion explains a state change.
2. **Calm** — confident curves, no theatrical bounce.
3. **Respectful** — `prefers-reduced-motion` snaps to final state for any animation > 100ms.

## 1. The motion stack

| Layer | Tool |
|---|---|
| CSS micro-interactions (hover, focus, color change) | Tailwind `transition-*` utilities |
| Component enter/exit (modal, drawer, dropdown) | Framer Motion (`<motion.div>`) |
| Layout animations (grid changes, list reorder) | Framer Motion's layout animations + `<LayoutGroup>` |
| Page transitions | Framer Motion at the layout level |
| Graph canvas animations | Sigma's built-in tweens + Web Worker for layout |
| Number tick-ups | Magic UI's `<NumberTicker>` |
| Card stack / marquee | Magic UI's components |
| Toast | Sonner (built-in physics) |
| Drawer (mobile-friendly) | Vaul (built-in physics) |

## 2. Easing curves

```css
--ease-out:     cubic-bezier(0.16, 1, 0.3, 1);
--ease-in-out:  cubic-bezier(0.4, 0, 0.2, 1);
--ease-spring:  cubic-bezier(0.34, 1.56, 0.64, 1);  /* very subtle bounce */
```

| Curve | When |
|---|---|
| `ease-out` | Content arrivals (page load, modal open, item insert) |
| `ease-in-out` | Layout shifts (sidebar collapse, panel resize) |
| `ease-spring` | Emphasis only — selected graph node, important state change |
| Linear | Progress bars, opacity fades on small UI like spinners |

## 3. Durations

| Token | ms | Use |
|---|---|---|
| `duration-instant` | 0 | reduced-motion fallback |
| `duration-fast` | 100 | hover, focus, tap, color change |
| `duration-default` | 150 | small transforms, content swap |
| `duration-medium` | 200 | modal open, drawer slide, card hover lift |
| `duration-slow` | 300 | page transition, expand/collapse |
| `duration-deliberate` | 400 | first-load reveal, hero animation, settle |
| `duration-pulse` | 1500 | repeated attention pulse (HITL pending) |

Anything > 400ms (except `pulse`) needs explicit justification.

## 4. Reduced-motion behavior

`@media (prefers-reduced-motion: reduce)` global rule (already in `globals.css`):

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

Plus Framer Motion's `useReducedMotion()`:

```tsx
const reduced = useReducedMotion();
const transition = reduced ? { duration: 0 } : { duration: 0.2, ease: 'easeOut' };
```

Specific reduced-motion overrides per component:

| Component | Default | Reduced-motion variant |
|---|---|---|
| Page enter | opacity 0→1 + y 8→0, 200ms | snap |
| Modal | scale 0.96→1 + opacity 0→1, 200ms | snap |
| Drawer | x 100%→0, 250ms | snap |
| Sigma graph layout | ForceAtlas2 animated settle | instant snap to final positions |
| HITL pulse | infinite 1.5s pulse | static glow |
| Cluster hover scale | scale 1→1.05 | no scale, just border-color change |
| Toast | slide + fade | snap |
| Card hover lift | translate-y -2px + shadow up | shadow change only |
| Number tick-up | 800ms count | static final value |

## 5. Component-by-component motion spec

### Sidebar

- Active-state indicator: 2px indigo bar slides between active items. 200ms ease-out.
- Collapse / expand: width transitions over 250ms ease-in-out.

### TopBar

- Static. No motion except for the theme toggle's sun/moon swap (200ms ease-out cross-fade).

### Navigation links

- Hover: bg-color transition 100ms.
- Active: bg + foreground color transition 150ms.
- Focus ring: instant.

### Buttons

- Hover: bg-color + border-color 100ms.
- Active (mouse-down): scale 0.98, 50ms ease-out.
- Disabled: opacity 0.5, no transition.
- Loading state: spinner appears, button content fades out 150ms.

### Cards (interactive)

- Hover: `translate-y(-2px) shadow-md`, 150ms ease-out.
- Reduced-motion: shadow change only.

### Form inputs

- Focus: ring fades in 100ms.
- Validation error: red ring fades in 200ms; error message slides down from 0 height to auto, 200ms ease-out.

### Modals (Dialog)

- Backdrop: opacity 0→0.6, 200ms.
- Content: scale 0.96→1 + opacity 0→1, 200ms ease-out.
- Close: reverse, 150ms ease-in.

### Drawer (Sheet / Vaul)

- Side drawer slide: 250ms ease-out.
- Bottom drawer: spring physics (Vaul default).
- Backdrop: matches Modal.

### Tooltip / Popover

- Show: opacity 0→1 + scale 0.95→1, 100ms ease-out, 100ms delay.
- Hide: 100ms ease-in.

### Dropdown / Select menu

- Open: opacity 0→1 + y -4→0, 150ms ease-out.
- Item hover: bg 100ms.

### Tabs

- Active indicator: 2px bar slides between tabs, 200ms ease-in-out.

### Accordion

- Expand: height 0→auto + opacity 0→1, 200ms ease-in-out.
- Collapse: reverse.

### Toast (Sonner)

- Enter: slide from y +24 + opacity 0→1, spring physics.
- Exit: slide to y +24 + opacity 1→0, 200ms ease-in.
- Action button hover: 100ms.

### Sigma graph canvas

- Initial layout: ForceAtlas2 200 iterations, animated settle over ~1.5s. Use Sigma's built-in `tween` system.
- Node selection: stroke width 1.5→3, scale 1→1.1→1.05 (settle), 250ms ease-spring.
- Edge hover: opacity 0.5→1, 100ms.
- Drag: instant follow.
- Zoom: 200ms ease-in-out.

### Graph node hover

- 100ms transition on stroke + size attributes.
- Connected edges fade to 100% opacity; non-connected to 20%.

### Progress bar (Pass progress)

- Width: linear interpolation matching actual progress; updates at most every 200ms.
- ETA text: cross-fade 200ms when value changes by > 1s.

### Number ticker (KPI cards)

- Magic UI's `<NumberTicker value={target} duration={800} />`. Ease-out.
- Only on initial mount; subsequent updates use cross-fade.

### Streaming feed (sample extractions)

- New item enters from top: slide-down 100ms + opacity 0→1 200ms.
- Old item exits via fade 200ms if scrolled out.

### Cluster bubble (Level B)

- Hover: scale 1.08, 150ms ease-spring.
- Click: scale settle to 1.05; stroke gains 2px.
- Merge animation: target cluster absorbs source (source scales to 0 over 300ms; target scales 1→1.1→1, 300ms ease-spring).
- Split animation: original cluster fades to 50% + new clusters fade in at 0% to 100%, 400ms ease-out.

### Verdict commit (HITL)

- On `Commit` click: button fades to spinner 150ms.
- Success: toast slides in.
- Card fades out 200ms; next card slides in from right, 200ms ease-out.

### Drag-and-drop (mapping wizard)

- Drag source ghost: 50% opacity, cursor `grabbing`.
- Drop zone highlight: bg + border color, 150ms.
- Drop confirmation: brief pulse on the dropped element, 300ms ease-spring.

### Citation drawer

- Slide up from bottom: y 100%→0, 250ms ease-out.
- Backdrop: opacity 0→0.4, 250ms.

## 6. Page transitions

Layout-level Framer Motion transition between routes.

```tsx
// app/layout.tsx (or a wrapper)
<AnimatePresence mode="wait">
  <motion.div
    key={pathname}
    initial={{ opacity: 0, y: 8 }}
    animate={{ opacity: 1, y: 0 }}
    exit={{ opacity: 0, y: -8 }}
    transition={{ duration: 0.2, ease: 'easeOut' }}
  >
    {children}
  </motion.div>
</AnimatePresence>
```

Cross-page navigation feels intentional but not slow. 200ms is the sweet spot.

## 7. Streaming-data animations

When SSE pushes new data:

- **List insert** (e.g., new HITL items appearing in inbox):
  - Slide down + fade in, 200ms.
  - Highlight the row with `bg-accent/10` for 1.5s then fade.
- **KPI count increment**:
  - NumberTicker animates the delta over 600ms.
  - Tiny `↑+1` indicator floats up + fades over 800ms.
- **Graph node materialization** (during pull):
  - Node appears at 0 size; scales to final size over 400ms ease-spring.
  - Connected edges fade in afterwards.
- **Progress bar update**:
  - Width animates over 200ms linear.

## 8. Loading state motion

Skeletons use Tailwind's `animate-pulse` (1.5s linear infinite). Customized in `globals.css` to use a smoother shimmer:

```css
@keyframes shimmer {
  0%   { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}

.skeleton {
  background: linear-gradient(
    90deg,
    hsl(var(--muted) / 0.3) 0%,
    hsl(var(--muted) / 0.5) 50%,
    hsl(var(--muted) / 0.3) 100%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
}
```

Reduced-motion: static `bg-muted/30`.

## 9. Empty state motion

Aceternity-style: hero icon does a subtle floating animation (translate-y -4→0→-4, 3s ease-in-out infinite).

Reduced-motion: static.

## 10. Feedback animations (success / error)

### Success (e.g., after committing a verdict)

- Check icon morphs in (svg path-draw animation), 400ms.
- Brief green pulse around the affected card, 600ms fade-in/out.
- Toast slides in (Sonner default).

### Error (e.g., connection failed)

- Affected field shakes (x: 0, -4, 4, -4, 4, 0 over 300ms).
- Red ring fades in.
- Error message slides down.

Reduced-motion: no shake; just immediate color + ring.

## 11. The HITL pulse

Per `05-trust-tier-ux.md`. Yellow pulsing ring for `hitl_pending` items:

```css
@keyframes hitl-pulse {
  0%   { box-shadow: 0 0 0 0 hsl(var(--warning) / 0.6); }
  70%  { box-shadow: 0 0 0 8px hsl(var(--warning) / 0); }
  100% { box-shadow: 0 0 0 0 hsl(var(--warning) / 0); }
}

.hitl-pending {
  animation: hitl-pulse 1.5s ease-out infinite;
}
```

Reduced-motion: static `box-shadow: 0 0 0 2px hsl(var(--warning) / 0.4)`.

## 12. Performance budget

- All motion runs at 60fps on Mahyar's GTX 1080.
- No layout thrashing — use `transform` + `opacity` only.
- No JS-driven animation for > 5 elements simultaneously (use CSS transitions instead).
- Sigma's WebGL renderer handles all graph motion at GPU speed.

## 13. Motion-free pages

The audit page deliberately has minimal motion — it's a forensic interface. Only:
- Row hover bg-color change (100ms).
- Filter changes update table without slide animation (instant).

Reasoning: when investigating a problem, the user wants speed and stability, not delight.

## 14. Animation accessibility

- Per WCAG 2.1: nothing flashes more than 3 times in any 1-second period (we never get close; 1.5s pulse is at 0.67Hz).
- All animations pausable via `prefers-reduced-motion`.
- No essential information is delivered via motion alone (motion is always supplemental to text + color).
- `aria-live="polite"` regions announce data changes that motion would otherwise communicate (e.g., new HITL items).

## 15. Out of V1.5 scope

- Lottie animations (V1.6 candidate for hero / onboarding).
- 3D motion / Three.js (V2).
- Scroll-driven animations (V1.6 — once we have a marketing surface for V2).
- Page-transition shared element morphs (V1.6 — Next.js View Transitions API).
