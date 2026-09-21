# HITL Review Flows — V1.5b

> One page per item type. Each flow ships under `/hitl/{type}`. Shared chrome: inbox at `/hitl`, `ReviewCard` + `VerdictPicker` + `BulkActionToolbar`, keyboard shortcuts (J/K/A/R/E/D/?).

## Inbox (`/hitl`)

Shows live counts per item type (TanStack Query refresh every 30s). Bulk-mode toggle for batchable types. "Resume where I left off" CTA per type if there's an in-progress claim.

| Item type | Source | Page |
|---|---|---|
| `alias_match` | V1 alias resolution (FR-3.2) | `/hitl/alias` |
| `conflict` | V1 conflict resolver step 6 | `/hitl/conflict` |
| `cluster_review` | V1.5b Pass-3 (new in V1.5b) | `/hitl/clusters` |
| `node_edge_proposal` | V1.5b Pass-4 (new) | `/hitl/proposals` |
| `multi_l1_claims` | V1.5a connector tier collision | `/hitl/multi-l1` |
| `cross_graph_link` | V1.5a CrossGraphLinker | `/hitl/crosslinks` |
| `judge_disagreement` | V1 3-vendor judge | `/hitl/judge` |
| `web_search_disagreement` | V1.5c WebVerificationAgent | `/hitl/escalated` |
| `tavily_unavailable` | V1.5c failure mode | `/hitl/escalated` |
| `escalated` | any reviewer-escalated item | `/hitl/escalated` |

## Per-type flow

### `/hitl/alias` (V1 carried)

**Body**: `AliasReviewBody` shows mention text (highlighted in context) + top-K canonical candidates (typically 3) with similarity scores + DITTO reranker scores.

**Verdicts**: `accept` (writes HAS_ALIAS + MENTIONS_SCHOOL), `reject` (writes UnresolvedEntity), `propose_alias` (add as new alias of canonical), `defer`.

**Empty state**: "No alias items pending. Last reviewed: {timestamp}."

### `/hitl/conflict` (V1 carried)

**Body**: `ConflictReviewBody` shows two claim cards side-by-side: claim A + claim B with `(subject, predicate, t_valid_year, source_tier, rank, evidence)`. Tier-clash banner if applicable.

**Verdicts**: `accept_a`, `accept_b`, `temporal_split` (different `t_valid_*`), `escalate` (to multi-vendor judge or HITL).

### `/hitl/clusters` (V1.5b new)

**Layout**: defaults to the Sigma.js Level B cluster map (`docs/08-ui/graph-level-views.md`); toggle to list-view via top-right pill.

**Body per cluster**: `ClusterReviewBody` with:
- Cluster label (Pass 3 summary)
- Description (1-sentence)
- Member count
- Sentiment ratio (if Pass 4 already touched it; else "Not yet analyzed")
- Sample posts (top 5 by representative score; full text on click)
- Status chip (`pending_review` / `approved` / `culled` / etc.)

**Verdicts**: `keep`, `cull`, `merge_into:<target_id>`, `split:<n>`, `mark_anomaly`, `defer`.

**Bulk actions**: select N clusters → "Apply same verdict" button → confirms. "Submit review batch" commits all pending decisions atomically and triggers the next Pass 4 sweep on approved clusters.

**Empty state**: "Pass 3 hasn't run on this corpus yet" + CTA.

### `/hitl/proposals` (V1.5b new)

**Body per proposal**: `ProposalReviewBody` with:
- Proposed type name (e.g., "Sentiment:Frustration" or "Edge:FRUSTRATED_WITH")
- Confidence
- Sample extractions (≥ 3 from Pass-4 output)
- Source posts for the samples
- Reasoning chain (the LLM's justification, if BAML captured it)

**Verdicts**: `accept` (added to feedback_log as positive example), `reject` (added to blocklist), `refine:<notes>` (rejected + creates a refined re-proposal), `defer`.

**Effect on next sweep**:
- Accepted: enters the active context block selection pool (subject to ADR-018 active-learning scoring; max 4 examples per template).
- Rejected: enters blocklist (subject to 50-cap LFU+LRU). Filtered post-hoc by `BlocklistFilter`.

### `/hitl/multi-l1` (V1.5a new)

**Body**: `MultiL1ReviewBody` shows two L1 sources' conflicting claims about the same `(subject, predicate, t_valid_year)`. Each side: connector name, raw value, source row reference, ingest timestamp.

**Verdicts**: `pick_winner_a`, `pick_winner_b`, `both_valid_temporal_split`, `escalate`.

**Effect**: winner gets `rank=preferred`; loser → `rank=deprecated`. Neither L1 node is modified.

### `/hitl/crosslinks` (V1.5a new)

**Body**: `CrossLinkReviewBody` shows side-by-side evidence: left = the existing canonical entity (with V1 / prior-connector context); right = the new entity from the new connector (with sample row data). Similarity score, sample shared mentions if any.

**Verdicts**: `accept` (SAME_AS written), `reject` (no link; pattern logged as negative example), `propose_alias` (add as alias without equivalence), `defer`, `escalate`.

### `/hitl/judge` (V1 carried)

**Body**: `JudgeBreakdown` shows the 3-vendor judge verdicts (Sonnet 4.6 + Gemini 2.5 Flash + GPT-4.1-mini per ADR-006) with per-vendor reasoning + confidence.

**Verdicts**: pick which vendor's verdict to honor; or `escalate` to Mahyar.

### `/hitl/escalated` (V1.5b new; V1.5c extends)

**Body**: depends on the underlying item type. Renders the item's standard body + an escalation note + previous attempted verdicts.

**Verdicts**: pick winner (item-type-specific), `re-escalate` (note added), `defer`.

V1.5c additions:
- `web_search_disagreement` body: shows signals A/B/C side-by-side with raw Tavily responses.
- `tavily_unavailable` body: original claim + options (retry web-verify, mark as research_need, accept one side without verification).

## Cross-cutting UX

**Empty states**: every queue page has a meaningful empty state with the timestamp of the last commit and a "View history" link.

**In-progress claims**: if a user opened a page mid-review and closed the tab, the next session shows "You have N items claimed — resume or release."

**Auto-claim timeout** (V1 carried): 24-hour idle claim auto-reverts to `pending`. UI shows reverted items with a "previously claimed by you" hint if recently expired.

**Confirmation modals**: destructive verdicts (`cull` on cluster, `reject` on cross-graph-link) prompt confirmation if user wasn't in batch mode.

**Undo**: each commit shows a 5-second toast "Decision committed — Undo". Undo writes a counter-decision row to `audit_log` and reverts graph state if reversible (alias / cross-graph / cluster verdicts are reversible; node-deletion is not).

## Keyboard shortcuts (per page)

- `J` / `K` — next / previous item
- `A` — accept (or first verdict in the picker)
- `R` — reject
- `E` — escalate
- `D` — defer
- `Enter` — submit commit
- `Esc` — cancel modal / clear selection
- `?` — shortcut help overlay
- `B` — toggle bulk mode (where supported)

## Accessibility

Each review page is keyboard-only navigable. Verdict picker uses radio-style buttons with `aria-pressed`. Side-by-side evidence rendered via `<article>` regions with proper headings. Screen-reader announces "Item X of Y" on load. Per `docs/08-ui/accessibility.md`.
