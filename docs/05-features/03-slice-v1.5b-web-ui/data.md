# Data Model — V1.5b

> Extends V1 + V1.5a. New tables + new audit kinds for the web UI + feedback loop.

## New SQLite tables

### `feedback_log` (per ADR-018; append-only)

```
feedback_id            TEXT  PRIMARY KEY
corpus_id              TEXT  NOT NULL
item_type              TEXT  NOT NULL              -- "node_proposal"/"edge_proposal"/"cluster_review"/"alias"/"conflict"/"cross_graph_link"/"multi_l1_claims"
pattern                TEXT  NOT NULL              -- raw pattern text (the proposed node/edge type + example payload)
pattern_canonical      TEXT  NOT NULL              -- normalized form for exact-match filtering
pattern_embedding      BLOB                        -- BGE-small embedding (384-dim, 1.5 kB)
prompt_template_id     TEXT                        -- which BAML template; NULL for non-extraction items
verdict                TEXT  NOT NULL              -- "accept"/"reject"/"refine"/"defer"
refinement             TEXT                        -- notes on `refine`
decided_by             TEXT  NOT NULL
decided_at             DATETIME NOT NULL
applied_in_sweep_first TEXT                        -- which Pass-4 sweep first reflected this decision
review_session_id      TEXT
confidence_at_decision REAL
```

Enforced append-only via DB trigger that rejects UPDATE + DELETE on `feedback_log`. Schema upgrades use new columns + NULL defaults, never destructive migrations.

### `feedback_loop_policy` (active-context-block weights + half-life)

```
policy_id              TEXT  PRIMARY KEY
corpus_id              TEXT  NOT NULL              -- or NULL = global default
template_id            TEXT                        -- or NULL = applies to all templates
w_relevance            REAL  NOT NULL DEFAULT 0.4
w_recency              REAL  NOT NULL DEFAULT 0.2
w_diversity            REAL  NOT NULL DEFAULT 0.3
w_freq                 REAL  NOT NULL DEFAULT 0.1
half_life_days         INT   NOT NULL DEFAULT 90
example_cap            INT   NOT NULL DEFAULT 4
blocklist_cap          INT   NOT NULL DEFAULT 50
diversity_threshold    REAL  NOT NULL DEFAULT 0.15
effective_from         DATETIME NOT NULL
created_by             TEXT  NOT NULL
notes                  TEXT
```

### `ui_sessions` (light session tracking; no auth in V1.5)

```
session_id             TEXT  PRIMARY KEY
opened_at              DATETIME NOT NULL
last_active            DATETIME NOT NULL
active_corpus_id       TEXT
view_url               TEXT
```

## New audit_log `kind` values

- `ui_view` — page load
- `ui_select` — node/cluster/row selected on a graph or table
- `ui_filter_change` — filter param updated
- `ui_review_commit` — single-item HITL commit
- `ui_batch_commit` — bulk-action commit
- `ui_settings_update` — settings page write
- `feedback_log_append` — new feedback_log row
- `blocklist_filtered` — extraction dropped by BlocklistFilter
- `feedback_loop_policy_update` — weights or caps changed
- `cluster_verdict` — keep/cull/merge/split
- `proposal_verdict` — accept/reject/refine

## Pydantic models (FastAPI + Zod-generated)

```
FeedbackLogEntry:
    feedback_id: str
    corpus_id: str
    item_type: Literal['node_proposal','edge_proposal','cluster_review','alias','conflict','cross_graph_link','multi_l1_claims']
    pattern: str
    pattern_canonical: str
    verdict: Literal['accept','reject','refine','defer']
    refinement: str | None
    prompt_template_id: str | None
    decided_by: str
    decided_at: datetime
    confidence_at_decision: float | None

ContextBlock:
    template_id: str
    examples: list[str]            # serialized positive examples (≤ 4)
    blocklist: list[str]           # serialized blocklist entries (≤ 50)
    context_hash: str              # sha256 of serialized block
    selected_at: datetime
    policy_id: str

FeedbackLoopPolicy:
    policy_id: str
    corpus_id: str | None
    template_id: str | None
    w_relevance: float
    w_recency: float
    w_diversity: float
    w_freq: float
    half_life_days: int
    example_cap: int = 4
    blocklist_cap: int = 50
    diversity_threshold: float = 0.15
    effective_from: datetime

ClusterReviewBatch:
    batch_id: str
    corpus_id: str
    decisions: list[ClusterDecision]
    submitted_at: datetime
    submitted_by: str

ClusterDecision:
    cluster_id: str
    verdict: Literal['keep','cull','merge_into','split','mark_anomaly','defer']
    target_id: str | None       # for merge_into
    n_targets: int | None       # for split
    notes: str | None

ProposalDecision:
    proposal_id: str
    pattern: str
    verdict: Literal['accept','reject','refine','defer']
    refinement: str | None
    notes: str | None

LevelStructuralResult / LevelClusterResult / LevelAnalyzedResult / CrossLinkResult:
    # Per ADR-012; each carries node/edge lists with full property convention
    ...

UIAuditEvent:
    event_type: Literal['view','select','filter_change','review_commit','batch_commit','settings_update']
    page_route: str
    selection_id: str | None
    filter_state: dict | None
    ts: datetime
```

## Graph schema (no new node/edge types in V1.5b)

V1.5b doesn't introduce new node or edge types beyond what V1.5a already added (`SAME_AS`). The graph viewer just consumes existing node/edge types via the three level-typed retrieval contracts.

## Cache key extension (per ADR-018)

Pass-4 content cache key:
```
hash(post_content + prompt_id + prompt_version + schema_hash + model_id + model_version + feedback_context_hash)
```

Adding `feedback_context_hash` means a feedback log update that affects the top-K invalidates only the affected template's cache entries, not the whole corpus cache.

## Storage estimates

- `feedback_log`: 1.5 KB/decision × ~5K decisions/year typical = ~7.5 MB/year. Negligible.
- `feedback_loop_policy`: usually one row, occasionally a handful for per-corpus / per-template overrides.
- `ui_sessions`: ephemeral; truncated to last 30 days.
- Audit log growth from UI events: ~10x baseline V1 rate (mostly `ui_view` + `ui_select` events). Acceptable; archive policy from V1 carries over.

## Indexes

- `feedback_log(corpus_id, prompt_template_id, decided_at DESC)` — primary query path for `FeedbackContextLoader`.
- `feedback_log(pattern_canonical)` — exact-match lookup for blocklist filter.
- `audit_log(ts DESC, kind)` — UI event filtering on the audit page.

## V2 reframe

- `ui_sessions` becomes a real session table with auth.
- `feedback_log` gains `tenant_id`.
- Per-tenant `feedback_loop_policy` overrides.
- Append-only constraint may relax to support compliance-deletion requests; bitemporal `t_to` instead.
