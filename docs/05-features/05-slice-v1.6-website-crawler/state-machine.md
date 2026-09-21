# State Machine — V1.6a Website-Crawl Ingestion

Two coupled state machines: **per-domain lifecycle** and **per-crawl-job lifecycle**.

## Per-domain lifecycle

```
                                         ┌──────────────┐
   register_domain (valid)               │              │
   ──────────────────────────────────►   │   active     │ ◄──┐
                                         │              │    │
                                         └──┬───┬───┬───┘    │ resume
                                            │   │   │        │
                            pause           │   │   │ auto-pause (5 failures or budget cap)
                            ─────────────►  │   │   │        │
                                            ▼   ▼   ▼        │
                                       ┌─────────────────┐   │
                                       │     paused      │   │
                                       │  (manual)       │   │
                                       └───────┬─────────┘   │
                                               │             │
                                               │             │
                                       ┌───────▼─────────┐   │
                                       │   auto_paused   │ ──┘
                                       │ (budget / err)  │
                                       └───────┬─────────┘
                                               │ user clicks "Resume"
                                               │ + cap cleared / failures acknowledged
                                               ▼
                                            (active)

   DELETE (soft) ──► deleted (terminal in active state graph;
                              row preserved for audit; cannot run; CANNOT be re-registered
                              under the same domain string — must `purge` first)
```

Transitions allowed:

| From | To | Trigger |
|---|---|---|
| (none) | `active` | `register_domain()` |
| `active` | `paused` | user click `pause`; MCP `pause_crawl_domain` |
| `paused` | `active` | user click `resume`; MCP analog |
| `active` | `auto_paused` | 5 consecutive failed runs OR `crawl_cap_hit` HITL emitted |
| `auto_paused` | `active` | user resolves HITL + clicks resume |
| `active` \| `paused` \| `auto_paused` | `deleted` | user click `delete` (soft delete, audit-preserved) |

## Per-crawl-job lifecycle

```
                                       cron tick / manual trigger
                                                 │
                                                 ▼
                                         ┌───────────────┐
                                         │   queued      │
                                         └───────┬───────┘
                                                 │ dispatcher picks up (every 5 min)
                                                 │ + status == "active"
                                                 ▼
                                         ┌───────────────┐
                                         │   running     │
                                         └───┬────────┬──┘
                                             │        │
                          all stages OK      │        │ exception / timeout / robots-disallow-all
                                             │        │
                                             ▼        ▼
                                       ┌──────────┐  ┌──────────┐
                                       │ succeeded │  │ failed   │
                                       └──────────┘  └──────────┘

                                       (running) ─── cap projection exceeded ──► capped
                                       (queued or running) ─── user cancel ────► cancelled
```

Transitions allowed:

| From | To | Trigger |
|---|---|---|
| (none) | `queued` | dispatcher schedules per cadence OR user `run-now` |
| `queued` | `running` | dispatcher picks up; concurrency budget has room |
| `running` | `succeeded` | all stages completed without unhandled errors |
| `running` | `failed` | unhandled exception, timeout, or robots-disallow-all |
| `running` | `capped` | L2 budget projection mid-run exceeds cap |
| `queued` \| `running` | `cancelled` | user clicks cancel via API/UI |
| any | (no further transition) | terminal states `succeeded` / `failed` / `capped` / `cancelled` |

## Stage progression (per crawl run)

Within a single `running` job, stages execute strictly in order:

```
  Fetch  ─►  L0 sitemap  ─►  L1 entity-tagged  ─►  L2 full GraphRAG
   │           │ writes Page/Sitemap/...                │ writes Cluster/Summary/Claim
   │           │                                        │
   │           ▼ (always runs)                          ▼ (runs only if domain.stage == "L2")
   │      mark_l0_done                              mark_l2_done
   │
   ▼ (always runs)
  mark_fetched
```

Gate conditions:

| Gate | Pass requirement |
|---|---|
| Enter L0 | At least 1 page successfully fetched in this run |
| Enter L1 | `domain.stage` ∈ {`L1`, `L2`} AND L0 wrote ≥ 1 new/changed `Page` |
| Enter L2 | `domain.stage` == `L2` AND budget projection (`avg_cost × queued × 1.2`) ≤ `max_usd_per_month - spent_month` |

If a gate fails:

| Gate failed | Behavior |
|---|---|
| L1 gate (no changed pages) | L1 skipped; job ends `succeeded` (incremental no-op) |
| L2 gate (budget) | L1 still runs; L2 skipped with `budget_capped` HITL item; job ends `capped` |

## Per-page lifecycle (bitemporal)

```
                       new URL discovered
                                │
                                ▼
                       ┌─────────────────┐
                       │  new Page node  │
                       │  t_valid_from=  │
                       │  fetch_time     │
                       │  t_valid_to=∞   │
                       └────────┬────────┘
                                │
                                │ re-crawl with same content_hash
                                │ → no-op (touch crawled_at only via bitemporal-friendly UPDATE)
                                │
                                │ re-crawl with new content_hash
                                ▼
                       ┌─────────────────┐
                       │  close prior    │
                       │  t_valid_to=    │
                       │  fetch_time     │
                       └────────┬────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │  open new Page  │
                       │  t_valid_from=  │
                       │  fetch_time     │
                       │  t_valid_to=∞   │
                       └─────────────────┘

                       URL absent ≥ 2 cadence cycles
                                │
                                ▼
                       ┌─────────────────┐
                       │  close Page     │
                       │  t_valid_to=    │
                       │  now            │
                       └─────────────────┘
```

`Chunk`, `Entity`, `Claim` nodes follow the same bitemporal-cascade close-then-open pattern when their parent `Page`'s `content_hash` changes.

## HITL escalation paths

| Condition | HITL item type | Auto-action while pending |
|---|---|---|
| Budget cap hit mid-run | `crawl_cap_hit` | Domain auto_paused |
| 5 consecutive failures | `crawl_chronic_failure` | Domain auto_paused |
| URL blocked after retries | `crawl_blocked` | URL skipped this run; next run retries unless added to per-domain blocklist |
| Mention ambiguous (0.75–0.95) | `entity_link_ambiguous` | `MENTIONS` edge left unlinked until resolution |
| L2 projection exceeds remaining budget | `budget_capped` | L2 skipped this run; L0+L1 still committed; job ends `capped` |

All HITL items render in `/hitl/escalated` per V1.5b plus V1.5c extensions.
