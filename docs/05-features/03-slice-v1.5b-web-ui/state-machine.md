# State Machines — V1.5b

> Three new state machines + the feedback-loop computation. UI-side state is React Query cache + URL params; backend-side persists everything to SQLite. All transitions audit-logged.

## 1. Cluster-review lifecycle

```
                       ┌─────────────────┐
                       │  pending_review │  (Pass 3 wrote the cluster; awaits user)
                       └────────┬────────┘
                                │ user opens /hitl/clusters and reviews
                                ▼
                       ┌─────────────────┐
                       │  in_review      │  (user has selected the cluster in UI)
                       └────────┬────────┘
                                │ verdict_submitted (single or batch)
                                ▼
              ┌─────────────────┼─────────────────┬─────────────────┬─────────────────┐
              ▼                 ▼                 ▼                 ▼                 ▼
           kept           culled            merged_into        split             marked_anomaly
           (Pass 4         (cluster         (members           (cluster          (kept but flagged
            runs on        excluded         re-attached to      partitioned       Status='anomaly'
            this cluster)  from next        target cluster;     into N new        for retrieval)
                           Pass 4)          this cluster        clusters;
                                            terminal)           members rebalanced
                                                                via re-clustering;
                                                                terminal)
              │                                  │
              ▼                                  ▼
        approved_for_pass4              (no further Pass 4 work)
        (terminal — Pass 4 picks
         this cluster up on next sweep)
```

**Invariants:**
- Pass 4 ONLY runs on clusters in state `approved_for_pass4` (= `kept` after batch commit). `culled` / `merged_into` / `split` (component clusters) / `marked_anomaly` clusters are excluded.
- `merge_into` requires `target_id` ∈ approved clusters. UI prevents merging into a culled target.
- `split` accepts a target N; re-clustering runs as a Phase-3 sub-job on the cluster's members. Resulting child clusters enter `pending_review` (recursive HITL).
- Batch commit is atomic at the queue level (single audit row covers the batch with `kind=ui_batch_commit`).

## 2. Node/edge proposal-review lifecycle

```
                       ┌──────────────┐
                       │  proposed    │  (Pass 4 surfaced; in HITL queue)
                       └──────┬───────┘
                              │ user opens /hitl/proposals
                              ▼
                       ┌──────────────┐
                       │  in_review   │
                       └──────┬───────┘
                              │ verdict_submitted
                              ▼
              ┌───────────────┼───────────────┬───────────────┐
              ▼               ▼               ▼               ▼
          accepted       rejected        refined           deferred
          (added as      (added to       (notes captured;  (stays in_review;
           positive       blocklist;      pattern modified  no feedback_log
           example in     pattern         per notes;        write)
           feedback_log;  filtered        new proposed
           may appear     post-hoc by     candidate enters
           in next        BlocklistFilter) proposed)
           context block)
              │               │               │
              ▼               ▼               ▼
        terminal         terminal         terminal (after edit cycle)
```

**Invariants:**
- Accepted proposals write to `feedback_log` with `verdict='accept'`. They may or may not surface in any given Pass-4 context block (selection is active-learning-scored per ADR-018).
- Rejected proposals write `verdict='reject'`. They appear in the blocklist subject to the 50-cap LFU+LRU eviction.
- `refined` is essentially "reject + create a new proposal." Two `feedback_log` rows: the original rejection + the new proposal (which routes back through `proposed`).
- `deferred` is a no-op on feedback_log — useful when the user wants to come back later.

## 3. Feedback-loop computation lifecycle (Pass-4 init time)

```
              Pass 4 init for (corpus, prompt_template_id)
                              │
                              ▼
                       ┌──────────────┐
                       │  load_log    │  (query feedback_log for this template)
                       └──────┬───────┘
                              │
                              ▼
                       ┌──────────────┐
                       │ score_examples│ (active-learning hybrid score)
                       └──────┬───────┘
                              │
                              ▼
                       ┌────────────────────┐
                       │ select_top_K_with_  │  (K=4 per ADR-018)
                       │ diversity_constraint│
                       └──────┬─────────────┘
                              │
                              ▼
                       ┌──────────────┐
                       │ evict_blocklist│ (cap=50; LFU+LRU eviction beyond cap)
                       └──────┬───────┘
                              │
                              ▼
                       ┌──────────────┐
                       │ build_block  │ (serialize examples + blocklist; hash)
                       └──────┬───────┘
                              │
                              ▼
                       ┌──────────────┐
                       │ check_cache  │ (cache key = ... + feedback_context_hash)
                       └──────┬───────┘
                              │
              ┌───────────────┼────────────────┐
              ▼                                ▼
        cache_hit                        cache_miss
        (return cached                   (invoke gateway with
         output)                          context-block-rendered
                                          BAML template)
                                              │
                                              ▼
                                        ┌──────────────┐
                                        │ blocklist_   │
                                        │ filter       │  (post-hoc safety net)
                                        └──────┬───────┘
                                               │
                                               ▼
                                        ┌──────────────┐
                                        │ write_cache  │
                                        │ + audit_log  │
                                        └──────────────┘
```

**Invariants:**
- Pure function of `(feedback_log_snapshot, prompt_template_id, scoring_weights)` → `ContextBlock`. Deterministic for fixed inputs (modulo embedding-similarity tie-break ordering, broken by canonical ID).
- `feedback_context_hash` is part of the Pass-4 cache key. Adding a new feedback_log row that affects the top-K invalidates only the affected template's cache, not the whole corpus.
- Settings-page edits to weights produce a new `policy_version`; existing caches keyed to the prior policy_version remain valid (we don't auto-invalidate on weight changes).

## 4. Cross-view selection lifecycle (UI-only, no audit unless interesting)

Selection state is `{nodeId | null}` in URL params + React Query cache. Selection persists across `/graph/structural` ↔ `/graph/clusters` ↔ `/graph/analyzed` switches via the shared `?selected={id}` param.

- Audit-logged: nothing on selection alone (high-volume noise). Only `ui_view` (page load) and `ui_filter_change` (filter param updates).
- Selection on `/graph/clusters` → cluster-detail panel; click "members" → switches to `/graph/structural?selected={member_id}` keeping selection state.

## Persistence

- All review-state transitions write `audit_log` rows with `entity_type='cluster'|'proposal'|'crosslink'|'multi_l1'|'alias'|'conflict'|'judge'`, `from_state`, `to_state`, `actor`, `reason`, `ts`.
- `feedback_log` is the source of truth for the feedback-loop computation; never UPDATEd / DELETEd (per ADR-018).
- Cluster + proposal verdicts also update the underlying graph (status flags, edge writes) atomically with the audit row.

## Replay

- Cluster-review batch decisions are replayable: from `audit_log` with `kind=ui_batch_commit` we can reconstruct which clusters were approved at which timestamp + what the resulting Pass-4 input set was.
- Feedback-loop computations are deterministic given `(feedback_log_snapshot, policy_version, prompt_template_id)`. Audit row records all three; replay is `select * from feedback_log where feedback_id <= snapshot_max_id`.

## Testing

Each lifecycle: unit-test (legal + forbidden transitions), property-based (audit-log invariants), integration (end-to-end through the UI). See `test-plan.md`.
