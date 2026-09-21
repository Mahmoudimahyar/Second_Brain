---
adr: 014
title: External database connector tiering — user-declared, defaults L2, L1 gated
status: accepted
date: 2026-05-24
deciders: Mahyar, Claude
supersedes:
superseded_by:
revision_history:
  - 2026-05-24 — proposed.
  - 2026-05-25 — accepted. V1.5a shipped `connect_data_source(engine, config, tier, confirm_l1_immutable=False)` with the L1 confirmation gate and the multi-L1 collision detector (`MULTIPLE_L1_CLAIMS`), per spec. Bitemporal tier history + connector audit log live. No drift.
---

# ADR-014 — External database connector tiering

## Context

V1's trust-tier schema (ADR-005) hardcodes the convention that **L1 = immutable ground truth**, populated only by curated upstream sources (ADEA + CODA) loaded via the L1 Excel/PDF adapters. The L1 invariant is enforced everywhere: FR-4.3 forbids `UPDATE` on L1 nodes; FR-6.1 forces conflicting non-L1 claims to `invalidated_by_official_data`.

V1.5a introduces external-database connectors. A user can now point the system at, say, a Postgres database that contains their organization's own school catalog. Three questions follow:

1. What tier is this connector's data?
2. Can it be L1?
3. If two L1 sources disagree, what wins?

Possible answers:
- Always L1 (treat user-connected DB as the new ground truth).
- Always L2 (L1 stays ADEA-only).
- User declares at connect-time, defaults L2 (the V1.5-R1 answer).
- Granular per-table.

## Decision

**User declares the tier at connect-time. Default is L2. L1 upgrade requires explicit confirmation.**

Specifically:

1. The `connect_data_source(engine, config, tier, confirm_l1_immutable=False)` MCP tool requires the caller to set `tier`. Valid values: `L1`, `L2`, `L3`, `L4`, `L5`. Default = `L2`.
2. Setting `tier=L1` without `confirm_l1_immutable=True` returns the structured error `INVALID_TIER_UPGRADE` with a message explaining the L1 contract.
3. The UI (V1.5b) renders the L1 option as a checked confirmation box: "I confirm this data source is immutable ground truth for my domain. Existing L1 nodes from other sources will not be overwritten by this connector." Submitting without checking it disables the L1 option entirely.
4. The chosen tier is stamped on every node + edge the connector materializes, via the same property convention used by every existing adapter.
5. **Multi-L1 collision**: if two L1 sources produce conflicting claims about the same `(subject, predicate, t_valid_year)`, both are written but the conflict resolver flags `MULTIPLE_L1_CLAIMS` and routes to HITL escalation rather than auto-resolving. L1 immutability holds at the per-source level; cross-L1 conflicts are a human-only decision.
6. **L2 connector vs existing L1**: an L2 claim conflicting with an existing L1 claim is flagged `invalidated_by_official_data` per the V1 conflict-resolution chain. The connector's claim is preserved (status flagged) but does not win.
7. **Re-tiering**: changing a connector's tier requires re-ingesting from scratch. Bitemporally, the old-tier edges have their `t_ingest_to` closed; new-tier edges open new `t_ingest_from`. No silent re-write.

A new audit-log kind `connector_tier_upgrade_attempt` records every L1 attempt (successful and rejected) with timestamp + actor.

## Consequences

**Positive:**
- L1 stays meaningful — it requires deliberate operator intent, not casual default.
- The default-L2 path supports the common case (user connects their team's DB, doesn't want to assert it's universally authoritative).
- Per-source L1 immutability is preserved; cross-L1 disagreement is surfaced for human resolution, not auto-resolved by trust-weighting.
- The V2 multi-tenant reframe inherits a clean model: per-tenant tier declarations don't accidentally pollute another tenant's L1 anchors.
- The L1 confirmation step doubles as user education — clicking it forces a moment of "do I really mean this?"

**Negative:**
- Two L1 sources can coexist (V1 had one). The HITL queue gains a new item type, `multiple_l1_claims`, which Mahyar must resolve manually.
- Re-tiering is destructive-ish: data isn't lost (bitemporal preserves history) but downstream consumers see a state change. UI must clearly warn.
- Granular per-table tiering (which V1.5-R1 considered) is deliberately deferred. A single connector = a single tier. If a user wants two tiers, they connect twice with different table projections.

**Neutral:**
- The L1 immutability invariant (no UPDATE on L1 nodes) is unchanged. ADR-005 stands.
- The conflict resolver's step ordering (ADR-006) is unchanged. We just add MULTIPLE_L1_CLAIMS to the failure-modes list.

## Alternatives considered (and rejected)

- **Always L1 for connected DBs** — rejected. Defeats the L1-as-authoritative-anchor model; means any user with a Postgres password becomes a "ground truth" oracle.
- **Always L2** — rejected. Constrains the generic-tool ambition. Some users will legitimately have ground-truth DBs (a customer-of-record system, a compliance registry); refusing to honor that is paternalistic.
- **Per-table tier** — appealing flexibility but doubles the UI complexity and creates per-table tier-collision questions. Deferred to V1.6 if real users want it.
- **Auto-detect tier from DB metadata** — too brittle. There's no reliable signal that says "this Postgres table is L1 vs L2."

## Implementation

V1.5a, Phase 4. Tests in `tests/ingestion/sources/test_tier_enforcement.py`.

V1.5b UI: tier selector in connector wizard with L1 confirmation modal.

## References

- ADR-005 — trust-tier schema (V1 invariant unchanged)
- ADR-006 — conflict resolution order (multi-L1 added as failure mode)
- `docs/05-features/02-slice-v1.5a-db-connector/requirements.md` FR-1.5a-4
- V1.5-R1 Q9 (DB tier) answer
