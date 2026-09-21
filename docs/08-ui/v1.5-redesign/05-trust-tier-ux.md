# Trust Tier UX — How users see, understand, and change tiers

> Trust tiers (L1–L5) are the central abstraction in SecBrain's data model (V1 ADR-005). The implementation has the data but no UI for it. This doc fixes that — visualization, exploration, and override.

## 0. The mental model the UI must teach

Most users won't read ADR-005. The UI has to communicate, implicitly, three things about every entity:

1. **What tier is this?** — At a glance.
2. **Why is it that tier?** — On demand.
3. **Can I (and should I) change it?** — Only when appropriate.

Failure to teach this means users either over-trust L5 forum posts or under-trust L1 ADEA data. Both are bad.

## 1. The visual vocabulary for tier

### Colors (per `01-design-system.md`)

| Tier | Color | Semantic |
|---|---|---|
| L1 | Amber/Gold | Canonical ground truth (immutable) |
| L2 | Teal | Verified secondary (curated, can be re-pulled) |
| L3 | Violet | Curated community (manual review baseline) |
| L4 | Zinc | Raw web (crawled, low trust) |
| L5 | Rose | Forum / social (high volume, individual claims unverified) |

### Shapes

In addition to color, every tier has a glyph component (for accessibility — color cannot be the only signal):

- L1: Star (5-point) — "ground truth"
- L2: Open book — "verified"
- L3: Bookmark — "curated"
- L4: Globe — "web"
- L5: Speech bubble — "forum"

### The `TierBadge` component

The atomic unit:

```
[★ L1]    [📖 L2]    [🔖 L3]    [🌐 L4]    [💬 L5]
```

Implementation:

```tsx
<TierBadge tier="L1" />              // small, default
<TierBadge tier="L1" size="lg" />     // larger, for headings
<TierBadge tier="L1" iconOnly />      // just the glyph; aria-label preserved
<TierBadge tier="L1" detailed />      // includes brief tooltip on hover
```

Visual:
- Background: `--tier-l{n}-bg`
- Foreground: `--tier-l{n}-fg`
- Border: `--tier-l{n}` 1px
- Glyph + text inline, `caption` size.
- Hover: tooltip with full tier description.

## 2. The `ProvenancePill` component

Every claim, every node, every edge has a `references` array (V1 NFR-4 invariant). `ProvenancePill` is the inline UI representation:

```
[★ L1 · preferred · 0.95]   "tuition_resident=$87,000"   [3 refs ▾]
```

Props:
- Tier badge.
- Rank chip (`preferred` / `normal` / `deprecated`).
- Confidence dot (color-coded per `01-design-system.md` confidence colors).
- Reference count (clickable to open the citation drawer).

Used everywhere a `Claim` is rendered — graph selection panel, HITL review cards, audit log, team dashboards.

## 3. The `TrustMeter` component

A horizontal-bar widget showing the composed trust calculation for an entity:

```
NYU School of Dentistry                              Trust score: 0.96
┌──────────────────────────────────────────────────────────────────┐
│  Tier       L1     ████████████████████████████████████████ 1.00 │
│  Rank       Pref   ███████████████████████████████░░░░░░░░ 0.85 │
│  HALO decay        ████████████████████████████████████░░░░ 0.92 │
│  Credibility       ███████████████████████████████████████░ 0.98 │
└──────────────────────────────────────────────────────────────────┘
ranking_score = tier × rank × decay × credibility = 0.96
```

This makes the ADR-007 ranking formula visible. Users can see *why* an entity ranked where it did, and can override (within the policy in §5).

Implementation uses visx for the bar chart. Animated on first render (200ms ease-out, per `08-motion-language.md`).

## 4. Surfacing tier in the graph canvas

Per `03-graph-visualization.md`:
- Node fill = tier-specific background (`--tier-l{n}-bg`).
- Node stroke = tier-specific color (`--tier-l{n}`), 1.5px.
- Optional glyph overlay (small icon in the NW corner of node).

In dark mode the fills are dim (low alpha) and strokes glow — the tier color essentially radiates.

When zoomed out (Level A on full corpus), tier color is the dominant visual signal — clusters of L5 (rose) posts emerge around L1 (gold) school anchors. Looks like little galaxies.

## 5. Where users can change tier

Strict policy (per ADR-014):

| Source | Default tier | Can user change? | Constraints |
|---|---|---|---|
| ADEA Excel / PDF (V1) | L1 | No (system-locked) | L1 anchor must stay L1 |
| External DB | L2 | Yes — at connect-time or in dashboard edit | L1 requires confirmation modal |
| Reddit JSONL | L5 | No | L5 enforced by adapter |
| SDN JSONL | L5 | No | Same |
| File upload (other Excel) | L2 | Yes | L1 requires confirmation |
| Website crawl (V1.6) | L4 | Yes | L1/L2 require confirmation + provenance evidence |

### The `TierSelector` component

When tier is changeable:

```
Tier  [L2 ▾]
   ┌───────────────────────────┐
   │ ○ L1 — Canonical truth    │
   │ ● L2 — Verified secondary │ ← current
   │ ○ L3 — Curated community  │
   │ ○ L4 — Raw web           │
   │ ○ L5 — Forum / social    │
   └───────────────────────────┘
```

Selecting L1 opens the confirmation modal:

```
┌────────────────────────────────────────────────────┐
│  Mark this source as L1 (canonical truth)?         │
│  ────────────────────────────────────────────────  │
│                                                    │
│  L1 sources are treated as immutable ground       │
│  truth. Existing L1 nodes from other sources       │
│  will NOT be overwritten by this connector.        │
│                                                    │
│  If two L1 sources disagree on the same fact,      │
│  the disagreement is escalated to HITL.            │
│                                                    │
│  ☐ I confirm this data is immutable ground truth   │
│    for my domain.                                  │
│                                                    │
│  [Cancel]  [Mark as L1]  ← disabled until checked │
└────────────────────────────────────────────────────┘
```

### Tier change has consequences

When a user changes a connector's tier from L2 → L1 on an existing source:
- All existing edges get `t_ingest_to` closed.
- New edges open with the new tier.
- If any existing L1 anchor conflicts → `multiple_l1_claims` HITL items created.
- Audit log: `connector_tier_upgrade_attempt` with old/new tier + actor.

Confirmation modal shows the scale of impact: "This will close `t_ingest_to` on 1,247 edges and re-open them as L1. Any conflicts with existing L1 will queue for HITL review (estimated 3 conflicts based on your current graph)."

## 6. Tier explorer view

A dedicated page `/graph/by-tier` (sub-view of Level C) for users who want to understand tier distribution:

```
┌──────────────────────────────────────────────────────────────────┐
│  Tier breakdown for corpus: v1_seed                              │
│  ────────────────────────────────────────────────────────────── │
│                                                                  │
│  L1  ★  124 schools · 18,130 metrics                             │
│  ████████████████████████████ 41% of nodes                       │
│                                                                  │
│  L2  📖 53 schools (Partner DB) · 312 cross-links                │
│  █████████ 11%                                                   │
│                                                                  │
│  L3  🔖 0 nodes (no L3 source connected yet)                     │
│                                                                  │
│  L4  🌐 0 nodes (V1.6: website crawl)                            │
│                                                                  │
│  L5  💬 2,000 posts · 13,874 comments · 3,700 authors           │
│  ████████████████████████████████████ 48%                       │
│                                                                  │
│  Sankey: how tiers reference each other (SAME_AS, MENTIONS, etc) │
│  [interactive Sankey chart, e.g., L5 mentions → L1 schools]      │
└──────────────────────────────────────────────────────────────────┘
```

Sankey rendered with visx — each "flow" is a tier-to-tier edge type (`MENTIONS_SCHOOL` from L5 to L1 is the thickest band; `SAME_AS` between L1 and L2 is a smaller band; etc.).

This view answers "where's my data coming from and how does it connect?"

## 7. Tier in HITL review

Every review card surfaces tier prominently:

```
┌─────────────────────────────────────────────────────────┐
│  Conflict #conflict:abc123                              │
│  ─────────────────────────────────────────────────────  │
│                                                         │
│  Subject:  school:nyu_dental                            │
│  Predicate: tuition_resident_2024-25                    │
│                                                         │
│  ┌──── Claim A ────┐         ┌──── Claim B ────┐       │
│  │ Value: $87,000   │         │ Value: $40,000  │       │
│  │ [★ L1 · pref]   │         │ [💬 L5 · norm]  │       │
│  │ ADEA SDE2 2024-25│         │ Reddit post     │       │
│  │ Confidence: 1.00 │         │ Confidence: 0.62│       │
│  └──────────────────┘         └─────────────────┘       │
│                                                         │
│  Resolution: L1 wins. Claim B status →                  │
│              invalidated_by_official_data               │
│                                                         │
│  Override:  [Accept resolution]  [Override...]  [HITL]  │
└─────────────────────────────────────────────────────────┘
```

The tier badges sit at the top of each claim card. The user sees at a glance that L1 should beat L5; the resolution is pre-applied; they only need to confirm or override.

## 8. Tier in retrieval results

Every result row in `/graph/search` and `/graph/analyzed` carries its provenance pill:

```
"NYU Dental tuition"
  ┌───────────────────────────────────────────────────────┐
  │ [★ L1 · pref · 1.00]  School:NYU                      │
  │ tuition_resident_2024-25 = $87,000                     │
  │ Source: ADEA SDE2 2024-25 (Table 3, row 42)            │
  └───────────────────────────────────────────────────────┘
  ┌───────────────────────────────────────────────────────┐
  │ [💬 L5 · norm · 0.62]  Reddit post                    │
  │ "I'm paying $40k for NYU this year"                    │
  │ Source: r/DentalSchool post abc123                     │
  │ Status: invalidated_by_official_data (red strike)      │
  └───────────────────────────────────────────────────────┘
```

The user never has to ask "which one do I trust?" — the visual makes it obvious.

## 9. Tier in per-team dashboards

PM / Social / Marketing dashboards each show tier composition for every insight:

```
Top pain point: "Tuition affordability anxiety"
  Volume:    248 mentions
  Sentiment: -0.71 (strong negative)
  Tier mix:  ███████████████░░░░░░░░░ L5 (76%)
              █░░░░░░░░░░░░░░░░░░░░░░  L2 (4%)
              ████░░░░░░░░░░░░░░░░░░░  L1 (20%)
  Sources:   r/DentalSchool, ADEA SDE2, Partner DB
```

The horizontal bar is a tiny stacked bar chart — colored by tier — that visually tells the PM "this pain point is mostly forum-driven (high volume but anecdotal)."

## 10. Filtering by tier

Every list and graph view has a tier-range filter:

```
Source tier minimum:  L4 ▾
   ┌──────────────────────────────────┐
   │ ○ L1 only                        │
   │ ● L1–L2 only (verified sources)  │ ← selected
   │ ○ L1–L3                          │
   │ ○ L1–L4                          │
   │ ○ All (include forum)            │
   └──────────────────────────────────┘
```

For PM dashboards, the default is "L1–L3" (filter out forum noise). For Social, default is "All" (forum signal is the point).

Per-team default filters live in `/settings/feedback-loop`.

## 11. Tier metrics and health

On the audit page, a "Tier health" panel:

```
Tier health (last 30 days)
─────────────────────────────────────
L1 anchors:     124    (stable)
L2 sources:     2      (1 added, 0 removed)
L1 conflicts:   3      (all resolved by HITL)
Cross-links:    53     (+12 this week)
Avg confidence:  0.81   (rising from 0.78)
```

Tells the operator if tier dynamics are healthy.

## 12. Tier in cross-graph linking

`/hitl/crosslinks` (cross-graph link review) is where tier comes alive:

```
┌─────────────────────────────────────────────────────────────────┐
│  Cross-graph link candidate                                     │
│  ─────────────────────────────────────────────────────────────  │
│                                                                 │
│  ┌── Anchor (existing) ──┐    ┌── Candidate (new) ──┐          │
│  │ school:nyu_dental      │    │ school:partner_2847  │          │
│  │ [★ L1 · ADEA SDE2]    │ ↔  │ [📖 L2 · Partner DB] │          │
│  │ Name: New York         │    │ Name: NYU Dental    │          │
│  │       University       │    │       Med           │          │
│  │ State: NY              │    │ State: NY           │          │
│  │ CODA code: 0832        │    │ Internal code: 2847 │          │
│  └────────────────────────┘    └─────────────────────┘          │
│                                                                 │
│  Similarity: 0.94      Confidence band: Auto-accept              │
│                                                                 │
│  If accepted: a SAME_AS edge will join these. Both nodes         │
│  preserved at their own tiers. Future claims about either        │
│  will be cross-queryable.                                        │
│                                                                 │
│  [Accept]  [Reject]  [Propose alias]  [Defer]                    │
└─────────────────────────────────────────────────────────────────┘
```

The tiers are loud — the user immediately sees "L1 anchor ↔ L2 candidate" and knows what kind of link this is.

## 13. Tier — common user questions answered by the UI

| User question | Where it's answered |
|---|---|
| "Why is this L5 forum post not believed?" | `ProvenancePill` tooltip + claim card showing L1 winning the conflict |
| "Why did the system mark this as anomaly?" | Selection panel "Lifecycle" timeline shows the conflict resolution step that flagged it |
| "Can I trust this person's post?" | Author selection panel shows `TrustMeter` breaking down credibility components |
| "What L1 anchors exist for this topic?" | Tier filter set to L1; entity search returns canonical entities only |
| "Where did this fact come from?" | Citation drawer expands every `references` link |
| "Why does my Partner DB have lower priority than ADEA?" | Default tier is L2; user can read tooltip on L1 selector or upgrade via the gated path |

## 14. Out of V1.5 scope

- Per-tenant tier policies (V2 multi-tenant).
- Custom tier definitions beyond L1–L5 (V1.6 may consider, e.g., "L0 = sacred / never-cross-link").
- Visual diff of "what would change if I re-tier?" (V1.6).
- Automated tier suggestions based on content analysis (V2).
