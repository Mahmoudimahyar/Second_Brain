# Data Model — V1.5c

> Extends V1 + V1.5a + V1.5b. New tables for web-search verification + per-team aggregations.

## New SQLite tables

### `web_search_cost`

```
call_id                TEXT  PRIMARY KEY
corpus_id              TEXT  NOT NULL
claim_hash             TEXT  NOT NULL
ts                     DATETIME NOT NULL
provider               TEXT  NOT NULL              -- "tavily" (V1.5c) / future: "brave"/"firecrawl"
operation              TEXT  NOT NULL              -- "qna_search"/"search"/"extract"
signal                 TEXT                        -- "A"/"B"/"C" (per ADR-016 v2 signals)
cost_usd               REAL  NOT NULL
latency_ms             INTEGER
success_bool           INTEGER NOT NULL
error_excerpt          TEXT
```

### `web_verification_runs`

```
run_id                 TEXT  PRIMARY KEY
claim_hash             TEXT  NOT NULL              -- content-addressable claim identifier
corpus_id              TEXT  NOT NULL
question_used          TEXT  NOT NULL              -- LLM-generated question for signal A
paraphrase_used        TEXT  NOT NULL              -- LLM-paraphrased for signal B
signal_a_verdict       TEXT                        -- "supports"/"refutes"/"unknown"
signal_a_evidence      JSON
signal_b_verdict       TEXT
signal_b_evidence      JSON
signal_c_verdict       TEXT                        -- agreement of Haiku + Gemini
signal_c_evidence      JSON                        -- top-URLs + extracts + per-vendor verdicts
final_verdict          TEXT                        -- "supports"/"refutes"/"escalated"/"research_need"/"tavily_unavailable"
final_confidence       REAL
combined_via           TEXT                        -- "2-of-3"/"3-of-3"/"escalated_disagreement"/"all_unknown"/"provider_failure"
cost_usd_total         REAL
latency_ms_total       INTEGER
ts                     DATETIME NOT NULL
cache_key              TEXT  NOT NULL
cache_hit              INTEGER NOT NULL DEFAULT 0
```

### `web_search_cache` (response cache)

```
cache_key              TEXT  PRIMARY KEY            -- hash(claim, context_summary, provider_versions)
run_id                 TEXT  NOT NULL REFERENCES web_verification_runs(run_id)
ts_stored              DATETIME NOT NULL
ts_expires             DATETIME NOT NULL            -- ts_stored + 7 days
```

### `team_rollups` (pre-computed daily aggregations)

```
rollup_id              TEXT  PRIMARY KEY
team                   TEXT  NOT NULL              -- "pm" / "social" / "marketing"
corpus_id              TEXT  NOT NULL
window_start           DATETIME NOT NULL
window_end             DATETIME NOT NULL
payload_json           TEXT  NOT NULL              -- the precomputed list of insights
computed_at            DATETIME NOT NULL
input_data_hash        TEXT  NOT NULL              -- fingerprint of source data; for invalidation
```

### `team_angle_cache` (LLM-generated suggested angles)

```
cache_key              TEXT  PRIMARY KEY            -- hash(team, item_id, current_data_hash, llm_version)
team                   TEXT  NOT NULL
item_id                TEXT  NOT NULL
angles_json            TEXT  NOT NULL              -- list of suggested angles
model_used             TEXT  NOT NULL              -- "gemini-2.5-flash-lite" / etc.
cost_usd               REAL
ts                     DATETIME NOT NULL
```

## New audit_log `kind` values

- `web_search_call` — single Tavily API call
- `web_search_cap_warning` — 80% cap threshold
- `web_search_cap_hit` — 100% cap; freeze further calls
- `web_verify_verdict` — verdict written to graph
- `web_verify_escalated` — escalation to HITL
- `team_dashboard_view` — page load
- `team_angles_generated` — LLM call to suggest angles

## Graph schema additions

No new node types. New edge type `WEB_VERIFIED` attached to existing claim edges:

```
WEB_VERIFIED:
  subject_id        # the claim being verified
  object_id         # the URL of the supporting evidence
  source_tier       # L4 (web; per V1 tier definitions)
  rank              # "preferred" if signal agreement strong, else "normal"
  confidence        # the agent's final_confidence
  references        # full web_verification_run JSON excerpt
  qualifiers        # {"signal": "A"|"B"|"C", "provider": "tavily", "extracted_excerpt": "..."}
  + standard bitemporal 4-tuple
```

## Pydantic models (FastAPI + Zod-generated)

```
VerifyClaimRequest:
    claim: str
    context: str | None
    corpus_id: str

VerdictResult:
    run_id: str
    final_verdict: Literal['supports','refutes','escalated','research_need','tavily_unavailable']
    final_confidence: float
    combined_via: str
    signal_a: SignalResult
    signal_b: SignalResult
    signal_c: SignalResult
    cost_usd_total: float
    latency_ms_total: int
    cached: bool

SignalResult:
    verdict: Literal['supports','refutes','unknown','disagreement','timeout']
    evidence: list[EvidenceItem]
    confidence: float | None

EvidenceItem:
    url: str
    excerpt: str
    provider: str
    operation: str

PainPoint:
    id: str
    label: str
    volume: int
    sentiment_ratio: float
    top_clusters: list[str]
    source_tier_mix: dict[str, int]
    last_30d_trend: list[int]    # daily volume sparkline
    audience_segment: str

TrendingTopic:
    id: str
    label: str
    volume: int
    sentiment_heat: Literal['negative','neutral','positive']
    trend_direction: Literal['up','flat','down']
    suggested_angle_preview: str

ContentGap:
    id: str
    topic: str
    volume: int
    sentiment_ratio: float
    supporting_cluster_ids: list[str]
    current_tier_coverage: dict[str, int]

SuggestedAngles:
    item_id: str
    team: Literal['pm','social','marketing']
    angles: list[str]
    model_used: str
    cost_usd: float
    cached: bool
```

## Cache keys

```
# Web-verify cache (7-day TTL)
sha256(claim_hash + context_summary_hash + tavily_model_version + llm_versions)

# Team-angles cache (invalidated when underlying data changes)
sha256(team + item_id + current_data_hash + llm_model_version)

# Team rollup cache (regenerated daily via Prefect flow)
team + corpus + window_start + window_end
```

## Indexes

- `web_search_cost(corpus_id, ts DESC)` — for cost-cap evaluation + telemetry dashboard.
- `web_verification_runs(claim_hash, ts DESC)` — replay lookup.
- `web_search_cache(cache_key)` + `web_search_cache(ts_expires)` — TTL eviction.
- `team_rollups(team, corpus_id, window_end DESC)` — load latest rollup.
- `team_angle_cache(team, item_id, ts DESC)` — load latest angles.

## Storage estimates

- `web_search_cost`: ~200 bytes/call × ~1000 calls/sweep = 200 KB/sweep.
- `web_verification_runs`: ~5 KB/verification (includes excerpts) × ~200 verifications/sweep = 1 MB/sweep.
- `web_search_cache`: ~5 KB/entry, 7-day TTL. Bounded by cache hit rate.
- `team_rollups`: ~50 KB/team/day. ~150 KB/day for 3 teams. Negligible.
- `team_angle_cache`: ~2 KB/entry. Bounded by user drill-down rate.

## V2 reframe

- `web_search_cost` gains `tenant_id` for per-tenant billing.
- `team_rollups` gains tenant scope + RBAC.
- Multi-provider records (Brave, Firecrawl, Exa) when V1.6 adds them.
