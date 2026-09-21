# State Machines — V1.5c

> Two new state machines (web-verify verdict + per-team insight). All transitions write `audit_log` rows.

## 1. Web-verify verdict lifecycle

```
                       ┌──────────────┐
                       │  triggered   │  (V1 conflict-resolver step 5 invoked WebVerificationAgent)
                       └──────┬───────┘
                              │ cache check
                              │
                 ┌────────────┴───────────┐
                 ▼                        ▼
            cache_hit              cache_miss
                 │                        │
                 │                        ▼
                 │                  ┌─────────────────┐
                 │                  │ build_question  │  (LLM call: BAML make_question_from_claim)
                 │                  └────────┬────────┘
                 │                           │
                 │                           ▼
                 │             ┌─────────────┴────────────┐
                 │             │ parallel async:          │
                 │             │  - Tavily QNA            │  signal A
                 │             │  - paraphrase + search   │  signal B
                 │             │  - extract + 2-LLM verify│  signal C
                 │             └─────────────┬────────────┘
                 │                           │
                 │                           ▼
                 │                  ┌─────────────────┐
                 │                  │ check_cost_cap  │
                 │                  └────────┬────────┘
                 │                           │
                 │                ┌──────────┴──────────┐
                 │                ▼                     ▼
                 │            cap_hit             cap_under
                 │            (freeze;            (continue)
                 │             escalate)
                 │                                      │
                 │                                      ▼
                 │                              ┌──────────────┐
                 │                              │ combine_signals│
                 │                              └──────┬───────┘
                 │                                     │
                 │                  ┌──────────────────┼──────────────────┬──────────────────┐
                 │                  ▼                  ▼                  ▼                  ▼
                 │            ≥2-of-3 agree      C disagree +       all unknown        provider failure
                 │            with confidence    A/B disagree                          (3 retries failed)
                 │            ≥ 0.7
                 │                  │                  │                  │                  │
                 │                  ▼                  ▼                  ▼                  ▼
                 │            verdict_written    escalated_disagreement  research_need_      tavily_unavailable
                 │            (graph claim with  (web_search_dis-        emitted             (HITL item)
                 │             references)       agreement HITL item)    (resolver fails
                 │                                                       step 5; HITL step 6)
                 │
                 ▼
          verdict_replayed
          (same as verdict_written but from cache)
```

**Invariants:**
- Every verdict (written or escalated) writes to `audit_log` with full `web_verification_run` JSON.
- `cap_hit` freezes all subsequent web-verify calls until next sweep window or manual reset.
- Provider failure (3 retries) ≠ disagreement — they route to different HITL item types.
- The cache key includes Tavily model version + LLM versions; vendor-side updates invalidate cache automatically.

## 2. Per-team insight lifecycle

```
                       ┌────────────────┐
                       │   triggered    │  (user opens /teams/{pm|social|marketing} or filter changed)
                       └───────┬────────┘
                               │
                               ▼
                       ┌────────────────┐
                       │  load_rollup   │  (read pre-computed daily aggregation)
                       └───────┬────────┘
                               │
                ┌──────────────┴──────────────┐
                ▼                             ▼
          rollup_fresh                  rollup_stale
          (< 24h old; use)             (≥ 24h old; trigger
                                       refresh in background;
                                       use stale this load)
                │                             │
                ▼                             ▼
          ┌──────────────┐            ┌──────────────┐
          │  render_list │            │  render_list │
          │  + suggest_  │            │  (no angles  │
          │  angles_on_  │            │  until rollup│
          │  demand      │            │  ready)      │
          └──────┬───────┘            └──────┬───────┘
                 │                            │
                 ▼                            ▼
            list_rendered              list_rendered_stale
            (user can drill-down       (banner "data may
             into any item)             be up to 24h old")
                 │
                 │ user clicks item
                 ▼
          ┌──────────────┐
          │  detail_load │  (suggest_angles invoked via gateway)
          └──────┬───────┘
                 │
                 ▼
          detail_shown
          (with citations + LLM-generated angles)
```

**Invariants:**
- Pre-computed daily roll-ups (computed by a Prefect flow `flows/team_rollups.py`) are the load-time source. Real-time aggregation never runs at page-load.
- `suggest_angles` is lazy — invoked only on detail-page open. Each call audit-logged with `kind=team_angles_generated`.
- Angles are NEVER auto-published or stored — they're regenerated on every detail-page open. Reproducibility is achieved via cache (`(item_id, current_data_hash, llm_version)`) not persistence.

## 3. Extensions to existing state machines

- **V1 conflict-resolution lifecycle** — step 5 now invokes `WebVerificationAgent` (above). Step 6 (HITL) only fires if web-verify cannot reach quorum.
- **V1.5b HITL queue** — gains item types `web_search_disagreement` + `tavily_unavailable`.
- **V1.5b proposal-review lifecycle** — Pass-4 proposals informed by web-verify verdicts can carry a `web_grounded` flag (purely informational; doesn't change the review flow).

## Persistence + audit

- `web_verification_run` JSON stored as `provider_evidence` on the resulting graph claim (or on the HITL item, if escalated).
- `web_search_cost` SQLite table appended per call (whether successful or failed).
- `audit_log.kind` extended with `web_search_call`, `web_search_cap_hit`, `web_search_cap_warning` (80% threshold), `web_verify_verdict`, `web_verify_escalated`, `team_dashboard_view`, `team_angles_generated`.

## Testing

Each lifecycle has unit + property-based + integration coverage per `test-plan.md`. Tavily calls are mocked via respx with pre-recorded fixtures in `tests/fixtures/v1.5c-tavily-responses/`.
