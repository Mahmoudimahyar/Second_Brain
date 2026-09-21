# Why the Codebase Drifted From the Documentation (Root-Cause Postmortem)

> Written 2026-05-29 after an external review found that several "accepted" / "Locked"
> architecture pillars are documented as done but are **not wired into the running V1
> pipeline** (and in some cases not implemented at all). This document explains *why*,
> with evidence, so the process fixes target the actual causes — not the symptoms.
>
> The fixes derived from this postmortem live in: `AGENTS.md` (§Wiring Gate, §Status
> discipline, §No horizontal expansion), `PROMPTS/SKILLS/06_VERIFICATION_BEFORE_COMPLETION.md`
> (doc↔code reconciliation step), and `docs/00-bootstrap/implementation-status.md`
> (the single source of truth for what is actually wired).

## TL;DR

The agent reliably produced **modules + slice-level tests + gate reports**, but "done"
was defined as *"this slice's acceptance criteria pass in isolation"* — not *"this
capability is invoked from the real end-to-end entrypoint and exercised on real data."*
So isolated, unit-tested modules were marked complete and the ADRs were flipped to
`accepted`, while the **integration wiring** that makes them part of the product was
silently skipped. Documentation was written in the **decision tense** ("we will do X /
X is Locked") and never reconciled against the **implementation tense** ("X is wired and
runs"). Five compounding factors below.

## Evidence of the drift (what review actually found)

| Claim in docs | Doc status | Code reality | Evidence |
|---|---|---|---|
| HALO per-edge-type temporal decay drives retrieval ranking | ADR-007 **accepted**; "Locked" in tech-stack | The three files ADR-007 lists under "Related code" **do not exist** (`src/conflict/halo_table.py`, `src/retrieval/ranking.py`, `tests/conflict/test_halo.py`). No decay anywhere in `src/retrieval/`. | `find`/`grep` 2026-05-29 |
| Signed-graph community detection resolves consensus | ADR-006 **accepted**; non-negotiable #5; "Locked" | Pass 3 uses plain `MiniBatchKMeans`; its own docstring says signed-graph is "V1.x … V2 follow-up." Not in the conflict resolver at all. | `src/extraction/pass3_clustering.py:8,188` |
| `ranking_score = tier × rank × decay × credibility`; retrieval "ranks by tier first, then recency, then consensus" | Product Principle #2; system-overview §5 | `query_graph` does substring seed lookup + BFS expansion; tier is only a **filter** (`source_tier_min`). No scoring, no decay, no consensus weight. | `src/retrieval/api.py:78-145` |
| Hybrid retrieval (BM25 + HNSW + RRF) | ADR-002 "Locked architecture" | `HybridIndex` type is referenced but **never constructed** in `src/`. Default path is the substring scan. | `grep "HybridIndex("` → none |
| 3-vendor LLM-as-judge breaks same-tier ties | ADR-006 **accepted**; non-negotiable #13 | Pipeline builds `ConflictResolver()` with **no judge and no web-verifier**; `LLMJudge`/`WebVerificationAgent` are never instantiated outside tests. Ties go straight to HITL. | `src/cli.py:899` |
| Bitemporal supersede sets prior `t_ingest_to` + new `t_ingest_from` atomically | non-negotiable #3; success-metric "100%" | No general supersede in the graph writer; `upsert_edge` is a plain `CREATE`. Only connector-lifecycle `t_ingest_to` writes exist (`registry.py`). | `src/graph/kuzu_client.py` |
| Graph DB "pending bake-off"; "Rejected: Kùzu" | tech-stack + system-overview | Bake-off **completed** 2026-05-21; ADR-001 **accepted Kùzu**; code runs on `KuzuGraphClient`. The two architecture docs were never updated. | ADR-001 vs tech-stack.md |

These are not random bugs. They share one shape: **the unit was built and tested; the
integration into the real path was not, and the docs were advanced to "done" anyway.**

## Root causes

### 1. "Definition of done" stopped at the slice boundary, not the system boundary
`AGENTS.md` "Done means done" required: acceptance criteria, tests pass, typecheck,
lint, docs updated, validation report. **None of those require the feature to be reachable
from the real entrypoint or run on real data.** A judge with 100% passing unit tests in
`tests/conflict/` satisfies every gate while `cli.py` never constructs it. The gate was
necessary-but-not-sufficient and the missing half (wiring) is exactly what drifted.

### 2. Documentation conflated "decided" with "built"
The "Locked vs pending" table and the ADR `accepted` status both mean *the decision is
made*. There was **no status that means "decided but not yet wired."** So "Locked" and
"accepted" were read — by the next agent and by the reader — as "implemented." ADR-007
even shipped a "Related code" section naming files that were never created, because the
ADR was written at decision time and never reconciled at implementation time.

### 3. Horizontal expansion outran vertical validation
`docs/00-bootstrap/kit/START_HERE.md` is explicit: *build one vertical slice, validate it, then the next.*
In practice the build went V1 → V1.5a → V1.5b → V1.5c → V1.5d → V1.6a — each adding a new
**feature area** (connectors, web UI, teams, crawler, web-verify) — while the **defining
V1 success slice** ("ADEA L1 + one subreddit → trust-tier graph with conflict resolution
+ HITL") never completed a single full forum ingest (see `round1-failure.md`, Q-028).
Each new slice had its own green gate report, so breadth looked like progress while the
core differentiators stayed stubbed.

### 4. Batch builds, not small reviewable diffs
Git history shows the entire V1→V1.5d landed as **one squashed commit** (`29f389b`:
764 files, 98,261 insertions, 2026-05-27), then V1.6a as 11 large phase commits. AGENTS.md
asks for "small, focused diffs"; a 98K-line commit is unreviewable, so wiring gaps inside
it were never caught by diff review. The "review your own diff as a skeptical senior
engineer" step (CLAUDE.md) cannot work on a 764-file diff.

### 5. The "research" that set the ADRs ran without live web access
`docs/03-research/research-log.md` opens with: *"WebSearch and WebFetch were denied in
this research session … Mahyar should re-run the live-source pass before ratifying the
ADRs."* That pass was never run. So the SOTA claims baked into the ADRs (e.g. "trust-tier
retrieval is under-published — we are inventing it"; "GraphRAG too expensive at scale";
"DITTO is SOTA") were never verified and are now **stale or overstated** (see
`R-010-sota-review-2026-05.md`). This is a *content*-accuracy drift distinct from the
wiring drift, but it has the same origin: a provisional artifact was promoted to
authoritative without the verification step that was explicitly flagged as pending.

### 6. Known but un-systematized
The team already logged this class of bug twice (GAP-042 "ADR-010 status drift",
GAP-043 "L2 node taxonomy drift") and fixed each instance by hand. The recurrence shows
ad-hoc patching wasn't enough; a **systematic guard** was missing.

## The fixes (and where they live)

1. **Wiring Gate** (AGENTS.md): a capability is not "done" until it is invoked from the
   real end-to-end entrypoint and exercised on real data. A module wired with
   `None`/no-op/stub is explicitly **not done** — it must be logged as a gap, not closed.
2. **Status discipline** (AGENTS.md + `implementation-status.md`): four states —
   `Decided` → `Built` (unit-tested) → `Wired` (reachable from the real entrypoint) →
   `Validated` (run on real data). "Locked"/"accepted" only ever means `Decided`. Every
   non-negotiable and every "Locked" row must cite the wiring site (`file:line`) where it
   is enforced, or be marked as a target.
3. **Doc↔code reconciliation step** (Verification skill): before claiming done, resolve
   each "Locked/done" claim to a wiring site; grep for stub wiring (`Resolver()` with no
   collaborators, unreferenced types); confirm the ADR "Related code" files exist.
4. **No horizontal expansion before the core slice is `Validated`** (AGENTS.md): no new
   feature area until the current vertical slice runs end-to-end on real data.
5. **Small diffs / one slice per PR; no squashed mega-commits** (AGENTS.md + CLAUDE.md).
6. **Research must be live-verified before an ADR leaves `proposed`** (research-protocol +
   continuous-research-policy): no `accepted` ADR may rest on `[needs live verification]`
   citations.

## How we verify the fixes worked

`implementation-status.md` is the audit surface. After the V1.7 patch, every row that the
docs call a non-negotiable or "Locked" must reach `Wired` or `Validated` with a cited
`file:line`, or be honestly marked `Decided`/`Deferred`. The CI doc-lint (new task in the
V1.7 prompt) fails the build if an ADR is `accepted` while its "Related code" files are
absent.
