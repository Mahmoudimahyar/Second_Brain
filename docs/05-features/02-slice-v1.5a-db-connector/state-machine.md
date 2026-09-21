# State Machines — V1.5a

> Three new state machines + extensions to V1's existing four (per `docs/05-features/01-slice-trust-tier-canonicalize/state-machine.md`). All transitions write `audit_log` rows. Invalid transitions return `INVALID_TRANSITION`.

## 1. Data source lifecycle

```
                       ┌──────────────┐
                       │ unregistered │
                       └──────┬───────┘
                              │ connect_data_source
                              ▼
                       ┌──────────────┐
                       │  registered  │  (credentials + tier validated, no schema yet)
                       └──────┬───────┘
                              │ discover_schema
                              ▼
                       ┌──────────────┐
              ┌───────►│  discovered  │  (SchemaSnapshot persisted)
              │        └──────┬───────┘
              │               │ suggest_mapping
              │               ▼
              │        ┌──────────────┐
              │        │   suggested  │  (MappingProposal generated; user editing)
              │        └──────┬───────┘
              │               │ commit_mapping
              │               ▼
              │        ┌──────────────┐
              │        │   mapped     │  (mapping committed; ready to pull)
              │        └──────┬───────┘
              │               │ pull_delta or pull_full_resync
              │               ▼
              │        ┌──────────────┐
              │        │   pulling    │  (active ingest job)
              │        └──────┬───────┘
              │               │ pull-complete
              │               ▼
              │        ┌──────────────┐
              │        │   active     │  (steady-state; subsequent pulls re-enter pulling)
              │        └──────┬───────┘
              │               │ pause (manual) / errored (auto)
              │               ▼
              │        ┌──────────────┐
              ├────────┤   paused or  │
              │        │   errored    │
              │        └──────┬───────┘
              │               │ resume / disconnect
              │               ▼
              │        ┌──────────────┐
              └────────┤disconnected  │  (retain_graph=True: bitemporal close;
                       │ (terminal)   │   retain_graph=False: hard delete materialized edges)
                       └──────────────┘
```

**Invariants:**
- `unregistered → registered` requires valid `tier`. L1 requires `confirm_l1_immutable=True`.
- `discovered → suggested` may be re-entered with `refresh=True` to re-suggest.
- `mapped → pulling` requires committed mapping; otherwise `MAPPING_NOT_COMMITTED`.
- `pulling` is internally segmented into per-table pulls; a partial failure rolls back the whole pull (atomic at the pull level).
- Re-tiering (`PATCH /sources/{id}` changing `tier`) transitions back to `mapped` and forces a full-resync.
- `disconnected` is recoverable: a subsequent `connect_data_source` with identical config returns the prior `source_id` and transitions back to `registered`.

## 2. Mapping decision lifecycle (per-table)

```
                       ┌────────────────┐
                       │   proposed     │  (MappingSuggester generated; not yet committed)
                       └───────┬────────┘
                               │ decision_threshold
                               │
                 ┌─────────────┼─────────────────────┐
                 ▼             ▼                     ▼
            conf ≥ 0.90  0.75 ≤ conf < 0.90     conf < 0.75
                 │             │                     │
                 ▼             ▼                     ▼
            auto_accepted   hitl_pending          rejected_by_threshold
                                │                     │
                                ▼                     ▼
                            committed             skipped (not materialized)
                            (after HITL +
                             optional edit)
```

**Per-table verdicts** at HITL commit:
- `accept_as_proposed`
- `accept_with_edits` (target_type or property mapping changed)
- `reject` (`mapping_type='skip'`)
- `defer` (stays in hitl_pending; can revisit later)

## 3. Cross-graph link lifecycle (per node-pair)

```
                       ┌──────────────┐
                       │  candidate   │  (CrossGraphLinker proposed a pair)
                       └──────┬───────┘
                              │ threshold gate
                              │
                 ┌────────────┼─────────────────────┐
                 ▼            ▼                     ▼
            conf ≥ 0.90   0.75 ≤ conf < 0.90    conf < 0.75
                 │            │                     │
                 ▼            ▼                     ▼
           auto_linked    hitl_pending           no_link
           (SAME_AS edge  (cross_graph_link      (candidates dropped;
            written       HITL item)              re-attempted on
            immediately)   │                       next ingest if more
                          │                       canonical mass appears)
                          │
                          ▼
                        Reviewer verdicts:
                          ├─ accept       → SAME_AS edge written (status='active')
                          ├─ reject       → no link; pattern logged as negative example
                          ├─ propose_alias → add alias to canonical entity, no SAME_AS
                          ├─ defer        → stays hitl_pending
                          └─ escalate     → multi_l1_claims (if both sides are L1) or general escalation
```

**Bidirectional semantics**: `SAME_AS` is stored as a single edge (canonical-ordered by node-id) with auto-mirroring on read. Re-linking after a rejection requires re-ingest + explicit `force_re_propose` flag.

## 4. Multi-L1 collision lifecycle (new HITL item type)

```
                       ┌─────────────────┐
                       │  detected       │  (two L1 sources claim conflicting values
                       │                 │   for same (subject, predicate, t_valid_year))
                       └────────┬────────┘
                                │ enqueue
                                ▼
                       ┌─────────────────┐
                       │  hitl_pending   │  (multi_l1_claims item)
                       └────────┬────────┘
                                │ reviewer verdict
                                ▼
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
        pick_winner_A      pick_winner_B      both_valid_temporal_split
              │                 │                 │
              ▼                 ▼                 ▼
        A becomes        B becomes          Two year-tagged
        rank=preferred   rank=preferred     entities; both kept
        B → deprecated   A → deprecated     with disjoint t_valid_*
        (terminal)       (terminal)         (terminal)
```

**Invariant**: neither L1 node is modified — only their incoming `rank` attribute on the conflicting claim edges is set. Per ADR-005 immutability.

## 5. Extensions to V1's state machines

- **Dump ingestion lifecycle (V1 §1)** — `register_dump(...)` is now a thin wrapper over `connect_data_source(engine='local_file', ...) + pull_delta(...)`. The V1 states (received → normalizing → extracting → resolving → reconciling → committed) remain inside `pulling`.
- **Claim conflict-resolution lifecycle (V1 §2)** — new failure mode `multiple_l1_claims` (above) added between `apply_source_trust` and `trust_weighted`. When both sides are L1, escalate immediately (do not attempt trust-weighting).
- **Alias-resolution lifecycle (V1 §3)** — `CrossGraphLinker` re-uses this state machine in cross-source mode. The `mention` state is replaced with `entity_pair`; the rest of the flow is identical.
- **HITL queue lifecycle (V1 §4)** — gains new item types: `mapping_proposal`, `cross_graph_link`, `multi_l1_claims`. No state-machine change otherwise.

## Persistence + audit

- Every transition writes an `audit_log` row with `kind=state_transition`, `entity_type` (`data_source` / `mapping_decision` / `crosslink` / `multi_l1`), `entity_id`, `from_state`, `to_state`, `actor`, `reason`, `ts`.
- Bitemporal: re-entering a state (e.g., re-discovery) closes the prior state's `t_ingest_to` and opens the new one's `t_ingest_from`.
- Replay: the audit log is the source of truth. The same graph state can be reconstructed from `audit_log + dump raw payloads + mapping_decisions` modulo non-deterministic clustering ordering (which V1.5a does not affect).

## Testing

Each state machine has:
- Unit-test class with full transition coverage (every legal transition + every forbidden transition).
- Integration test that walks a representative data source through all five state machines end-to-end.
- Property-based test (hypothesis) asserting (a) only legal transitions happen, (b) every transition is audit-logged, (c) state is recoverable from audit log alone.

Implementation hint (carried from V1): encode each state machine as `enum + transition_table: dict[(state, event), state] + apply_transition() function`. Avoid scattering transition logic across business code.
