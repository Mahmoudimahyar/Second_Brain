# State Machines

The V1 slice has four state machines that must be implemented + tested explicitly. State transitions are first-class: every transition writes an `audit_log` row. Invalid transitions are rejected with `INVALID_TRANSITION` error.

## 1. Dump ingestion lifecycle

States a `Dump` passes through after `register_dump(...)` is called.

```
                        ┌─────────────┐
                        │  received   │  (manifest validated, payloads hashed, raw stored)
                        └──────┬──────┘
                               │ adapter selected per source_tier × schema_hint
                               ▼
                        ┌─────────────┐
                        │ normalizing │  (source-type adapter produces canonical records)
                        └──────┬──────┘
                               │ canonical records written to staging
                               ▼
                        ┌─────────────┐
              ┌────────►│ extracting  │  (cascade pipeline runs Stage 1 → 2 → 3)
              │         └──────┬──────┘
              │                │ extracted claims + entities
              │                ▼
              │         ┌─────────────┐
              │         │  resolving  │  (entity resolution + alias snap)
              │         └──────┬──────┘
              │                │ resolved + unresolved sets
              │                ▼
              │         ┌─────────────┐
              │         │ reconciling │  (conflict resolver runs 6-step order)
              │         └──────┬──────┘
              │                │ committed claims / hitl-queued / web-verify-queued
              │                ▼
              │         ┌─────────────┐
              │         │  committed  │  (all graph writes done; t_ingest_from finalized)
              │         └─────────────┘
              │
              │     any stage     ┌─────────────┐
              └──────────────────►│   failed    │  (dump rollback; audit_log captures reason)
                                  └─────────────┘
```

**Transition rules:**
- All transitions are idempotent: replaying `register_dump` with identical content-hash → no-op + receipt returns prior state.
- `failed` is terminal for that ingestion attempt but the same content can be re-attempted later (different `attempt_id`).
- `committed` is terminal; subsequent re-ingest with different content for the same logical source becomes a new `Dump` row.

## 2. Claim conflict-resolution lifecycle

Each extracted claim passes through this until terminal state.

```
                                       ┌────────────┐
                                       │  proposed  │  (just extracted)
                                       └─────┬──────┘
                                             ▼
                                       check_l1_clash
                                             │
                                ┌────────────┴───────────┐
                                ▼                        ▼
                ┌───────────────────────┐    ┌───────────────────────┐
                │ invalidated_by_       │    │   check_temporal      │
                │ official_data         │    │   disambiguation      │
                │ (terminal — L1 wins)  │    └──────────┬────────────┘
                └───────────────────────┘               │ different t_valid_*?
                                                        ▼
                                       ┌─────────────────────────┐
                                       │  temporal_split          │
                                       │  (year-tagged versions)  │
                                       │  (terminal — both kept)  │
                                       └─────────────────────────┘
                                                        │ same year, conflicting
                                                        ▼
                                       ┌────────────────────────┐
                                       │ apply_source_trust     │
                                       │ (tier × rank × cred)   │
                                       └──────────┬─────────────┘
                                                  ▼
                                       ┌────────────────────────┐
                                       │ trust_weighted         │
                                       │ (winner rank=preferred;│
                                       │  loser rank=normal)    │
                                       │ (terminal)             │
                                       └────────────────────────┘
                                                  │ still ambiguous? (e.g., trust tied)
                                                  ▼
                                       ┌────────────────────────┐
                                       │ signed_graph_cluster_  │
                                       │ check                  │
                                       └──────────┬─────────────┘
                                                  ▼
                            ┌─────────────────────┴────────────────────┐
                            ▼                                          ▼
                  ┌───────────────────────┐               ┌───────────────────────┐
                  │ consensus_cluster     │               │ anomaly               │
                  │ (terminal — preferred │               │ (preserved, queryable │
                  │  is majority)         │               │  with                 │
                  └───────────────────────┘               │  include_anomalies)   │
                            │                             └───────────────────────┘
                            │  L1 missing + L5 disputes
                            ▼
                  ┌───────────────────────┐
                  │ web_verify_queued     │  (emits research_need)
                  └──────────┬────────────┘
                             ▼
                  ┌───────────────────────┐
                  │ awaiting_crawler      │  (idle until crawler delivers + reingest happens)
                  └───────────────────────┘

  Anywhere above where the resolver can't decide → hitl_pending → hitl_committed (terminal).
```

**Invariants:**
- L1 nodes are never modified by this state machine. Only the L5 (or L2/L3/L4) side of the conflict is flagged.
- `invalidated_by_official_data`, `temporal_split`, `trust_weighted`, `consensus_cluster`, `anomaly`, `hitl_committed` are all terminal.
- LLM-as-judge is invoked at most once per claim, only between `apply_source_trust` and `trust_weighted`, and only for same-tier same-year tie-breaks (A-031).

## 3. Alias-resolution lifecycle (entity-snap)

```
              ┌──────────────┐
              │  mention     │  (Stage 1 found a candidate span)
              └──────┬───────┘
                     ▼
              ┌──────────────┐
              │  blocking    │  (BGE-small HNSW top-K)
              └──────┬───────┘
                     ▼
              ┌──────────────┐
              │  reranking   │  (DITTO / DistilBERT NLI)
              └──────┬───────┘
                     ▼
              decision_threshold
                     │
       ┌─────────────┼─────────────────────┐
       ▼             ▼                     ▼
  sim ≥ 0.90    0.75 ≤ sim < 0.90      sim < 0.75
       │             │                     │
       ▼             ▼                     ▼
  auto_accept    hitl_pending         unresolved_entity
  (terminal)    (terminal until         (terminal — preserved
                 reviewer commits;       as a marker node;
                 then accept |           re-attempted on next
                 reject |                ingest if new aliases
                 propose_alias)          appear)
```

**Transition rules:**
- Auto-accept writes `HAS_ALIAS` from canonical entity to alias-string + a `MENTIONS_SCHOOL` (etc.) edge from the mention's host post/comment to the canonical entity.
- HITL accept = same as auto-accept + the alias is added to `alias` table with `alias_source = 'hitl'` and full confidence.
- HITL reject = creates an `UnresolvedEntity` node + the mention is *not* connected to any canonical entity.
- HITL propose-alias = the reviewer suggests a new canonical entity (e.g., a school not in ADEA L1); routed to `propose_new_node_type` HITL flow (out of V1 slice; deferred to V1.x or covered by a separate HITL item type).
- `unresolved_entity` is **not deleted** even on subsequent ingests — re-attempted automatically once the alias table or canonical universe grows.

## 4. HITL queue lifecycle

```
            ┌──────────┐
            │  pending │  (enqueued by another state machine)
            └─────┬────┘
                  ▼ hitl pull (claims one)
            ┌──────────┐
            │  claimed │  (reviewer has the YAML file open)
            └─────┬────┘
                  ▼ hitl commit  | hitl escalate  | claim_timeout
       ┌──────────┼───────────────┬──────────────┐
       ▼          ▼               ▼              ▼
  committed  escalated    pending (timeout)   re-claimed
  (terminal) (Mahyar      back into queue     (same flow)
              review)
```

**Timeout / re-claim:**
- A claimed item that has no commit/escalate within 24 hours auto-reverts to `pending` (configurable). The reviewer's draft is preserved as a comment for the next claimer.

**Escalation:**
- `escalated` items go to a separate sub-queue (`hitl_queue WHERE status = 'escalated'`). Mahyar reviews these explicitly.

## Persistence + auditing

- Every state transition writes `audit_log` (FR-11). `kind = 'state_transition'`, fields include `entity_type`, `entity_id`, `from_state`, `to_state`, `actor` (system | reviewer:<id>), `reason`, `ts`.
- Bitemporal: state transitions update `t_ingest_to` on the prior state's edge and set `t_ingest_from` on the new state's edge.
- Replay: the audit log is the source of truth. Rebuilding the graph from `audit_log` + `dump` raw payloads must produce an identical graph (modulo non-deterministic clustering ordering).

## Testing

Each state machine has:
- A unit-test class per machine with full transition coverage (every legal transition + every forbidden transition).
- An integration test that walks a representative dump through all four state machines end-to-end.
- A property-based test (hypothesis) that asserts: (a) only legal transitions happen, (b) every transition is audit-logged, (c) state is recoverable from audit log alone.

Implementation hint: encode state machines as `enum` + `transition_table: dict[(state, event), state]` + a single `apply_transition()` function — avoid scattering transition logic across business code.
