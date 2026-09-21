# API

> V1 slice exposes a minimal MCP surface (inbound + outbound) and the internal Python module-level APIs that compose to deliver it. Vendor-portable: every external-model call goes through the model gateway (ADR-011, pending R-009).

## MCP — Inbound (V1 internal callers consume these)

> Two distinct MCP deployments. This section is the **V1 product engine MCP** (not the `tools/graphrag/` repo MCP server).

### `query_graph`

```
query_graph(
  query: str,
  source_tier_min: Optional[Literal["L1","L2","L3","L4","L5"]] = None,
  time_range: Optional[Tuple[datetime, datetime]] = None,
  as_of: Optional[datetime] = None,                 # bitemporal: reconstruct graph state
  traversal_depth: int = 3,
  include_anomalies: bool = False,
  limit: int = 50
) -> list[QueryResult]
```

`QueryResult` shape:
```
{
  "node_id": str,
  "node_type": str,             # e.g., "School" / "Post" / "Claim"
  "properties": dict,
  "source_tier": "L1"|"L2"|"L3"|"L4"|"L5",
  "rank": "preferred"|"normal"|"deprecated",
  "references": [<source_dump_id_or_post_id>, ...],   # citation traceability
  "confidence": float,                                # 0-1
  "t_valid_from": datetime,
  "t_valid_to": Optional[datetime],
  "path_explanation": [{"edge_type": str, "from": node_id, "to": node_id}, ...]
}
```

p95 latency target: < 250 ms (NFR-1). Citation traceability ≥ 99% (NFR-4).

### `get_canonical_entity`

```
get_canonical_entity(
  alias: str,
  entity_type: Literal["School","Program","Specialty"]
) -> CanonicalEntity
```

`CanonicalEntity`:
```
{
  "canonical_id": str,
  "canonical_name": str,
  "type": str,
  "aliases": [str],            # known alias list
  "source_tier": "L1",
  "rank": "preferred",
  "references": [<source_dump_id>],
  "match_confidence": float    # how confident the alias-snap is
}
```

p95 < 50 ms. Used by extraction pipeline AND by external agents wanting to canonicalize.

### Out-of-V1 inbound (deferred to later slices)

- `search_by_topic(topic, source_tier_min, time_range)` — V1.x
- `get_user_credibility(user_id, topic)` — V1.x
- `get_topic_consensus(topic, time_range)` — V1.x (depends on signed-graph community detection becoming a retrieval primitive)

## MCP — Outbound (the engine calls these against a separate crawler system)

### `register_dump`

```
register_dump(
  source_tier: Literal["L1","L2","L3","L4","L5"],
  manifest: DumpManifest,
  payload_paths: list[Path]
) -> DumpReceipt
```

`DumpManifest`:
```
{
  "source_name": str,                              # e.g., "ADEA_Report_2_2024-25"
  "source_url": Optional[str],
  "source_tier": Literal["L1","L2","L3","L4","L5"],
  "rank_default": "preferred"|"normal"|"deprecated",
  "license": str,                                  # e.g., "ADEA proprietary; internal use only V1"
  "provenance": dict,                              # crawler identity, fetch timestamp, etc.
  "t_valid_range": Tuple[datetime, datetime],      # cycle year span
  "schema_hint": Optional[dict]                    # adapter-routing hint
}
```

`DumpReceipt`:
```
{
  "dump_id": str,
  "content_hashes": list[str],                     # one per payload file
  "t_ingest_from": datetime,
  "validation_result": "ok" | "rejected_<reason>",
  "duplicate_of": Optional[str]                    # if idempotent re-ingest
}
```

Idempotency: identical content-hashes → no-op + same receipt.

### `get_gaps`

```
get_gaps(
  topic_filter: Optional[str] = None,
  source_tier_filter: Optional[Literal["L1","L2","L3","L4","L5"]] = None,
  limit: int = 100
) -> list[Gap]
```

`Gap`:
```
{
  "topic": str,
  "source_tier": str,
  "gap_reason": str,           # "no_L2_source_for_school_<id>" / "no_recent_L1_for_topic" etc.
  "priority": "high"|"medium"|"low",
  "suggested_crawl": Optional[dict]    # hint to crawler
}
```

### `get_research_needs`

```
get_research_needs(limit: int = 100) -> list[ResearchNeed]
```

`ResearchNeed`:
```
{
  "research_need_id": str,
  "topic": str,
  "conflicting_claim": dict,       # the L5 cluster
  "l1_value": Optional[dict],      # the L1 contradiction (if any)
  "reason": str,
  "suggested_sources": list[str]   # canonical URLs the crawler should try
}
```

### Additional outbound (pending Q-021)

- `is_url_ingested(url)` → bool
- `get_topic_state(topic)` → current graph summary on a topic
- `get_pending_verifications()` → list of conflict candidates needing official-source confirmation

## Internal Python APIs (module-level, composable)

> Every component below is its own module under `src/`. Each has a public Python API. MCP wrapping is per the ADR-012 policy (component-MCP rule pending R-009). Default: API-first, MCP only where agent-callable.

### Ingestion plane

```python
# src/ingestion/api.py
class IngestionService:
    def register_dump(self, source_tier, manifest, payload_paths) -> DumpReceipt: ...
    def get_dump(self, dump_id) -> Dump: ...
    def list_dumps(self, source_tier_filter=None) -> list[DumpReceipt]: ...

# Adapter registry (pluggable per FR-1.2..1.4)
class SourceAdapter(Protocol):
    source_tier: str
    def normalize(self, raw_payload) -> Iterable[CanonicalRecord]: ...
    def extract_seeds(self, canonical_records) -> Iterable[SeedEntity]: ...
```

### Cascade extraction

```python
# src/extraction/cascade.py
class CascadePipeline:
    def __init__(self, gateway: ModelGateway, er: EntityResolver, cache: ExtractionCache): ...
    def stage1_filter(self, doc: Document) -> Stage1Result: ...
    def stage2_extract(self, doc: Document) -> Stage2Result: ...
    def stage3_api(self, doc: Document, prompt_id: str) -> Stage3Result: ...
    def run(self, doc: Document) -> ExtractionResult: ...
```

### Entity resolver

```python
# src/er/api.py
class EntityResolver:
    def __init__(self, embedder, reranker, canonical_index: CanonicalIndex): ...
    def resolve(self, mention: str, entity_type: str, top_k: int = 10) -> list[ResolutionCandidate]: ...
    def snap(self, mention: str, entity_type: str) -> SnapResult:
        """auto-accept | hitl | reject per FR-3 thresholds"""
```

### Conflict resolver

```python
# src/conflict/api.py
class ConflictResolver:
    def reconcile(self, claim: Claim, existing_claims: list[Claim]) -> ResolutionOutcome: ...
    # outcome: l1_clash_invalidated | temporal_split | trust_weighted | anomaly | hitl_pending
```

### Model gateway (V1 — pending ADR-011 from R-009)

```python
# src/gateway/api.py
class ModelGateway:
    """Vendor-portable interface. Picks model per task per ADR-011 selection criteria."""
    def complete(
        self,
        task: TaskID,                     # e.g., "stage3.sentiment", "judge.tie_break"
        prompt: BAMLPrompt,
        inputs: dict,
        schema: Optional[type[BaseModel]] = None,
        cache_ttl: int = 3600              # mandatory; lint-enforced
    ) -> GatewayResponse:
        """Routes to Anthropic / OpenAI / Gemini / open-weight per task config."""

    def fallback_chain(self, task: TaskID) -> list[VendorModel]: ...
    def cost_estimate(self, task: TaskID, input_tokens: int, output_tokens: int) -> float: ...
```

`GatewayResponse`:
```
{
  "vendor": "anthropic"|"openai"|"gemini"|...,
  "model": str,
  "output": <parsed schema instance>,
  "input_tokens": int,
  "output_tokens": int,
  "cached_input_tokens": int,
  "cost_usd": float,
  "latency_ms": float,
  "cache_hit": bool,
  "audit_id": str
}
```

### Bitemporal graph writer

```python
# src/graph/bitemporal.py
class BitemporalWriter:
    def upsert_edge(self, edge: Edge, ingest_time: datetime) -> EdgeID: ...
    def supersede(self, edge_id: EdgeID, t_ingest_to: datetime) -> None: ...
    def as_of(self, time: datetime) -> GraphSnapshot: ...
```

### HITL queue

```python
# src/hitl/api.py
class HITLQueue:
    def enqueue(self, item: HITLItem) -> ItemID: ...
    def pull(self) -> Optional[HITLItem]: ...
    def commit(self, item_id: ItemID, decision: Decision) -> None: ...
    def list(self, status_filter=None) -> list[HITLItem]: ...
```

### Audit log

```python
# src/observability/audit.py
class AuditLog:
    def log_extraction(self, **fields) -> None: ...    # FR-11.1
    def log_retrieval(self, **fields) -> None: ...     # FR-11.2
    def log_hitl(self, **fields) -> None: ...          # FR-11.3
    def query(self, since=None, kind=None) -> list[AuditRow]: ...
```

## API error model (single shape across the engine)

```
{
  "error_code": str,         # e.g., "VALIDATION_FAILED" / "L1_IMMUTABLE_REJECT" / "GATEWAY_ALL_VENDORS_FAILED"
  "message": str,            # human-readable
  "context": dict,           # debugging context (input fingerprints etc.)
  "retry_safe": bool         # whether the caller can retry without dedup risk
}
```

Codes catalog in `docs/06-api/error-codes.md` (TBD next batch).

## Backwards-compatibility policy (V1 → V1.x)

- Inbound MCP tool signatures are append-only (no breaking signature changes).
- New tools can be added without bumping a major version.
- Output schemas are versioned via `"_schema_version": int` in the response payload.
- Breaking changes require an ADR.

## Out-of-scope this slice

- `search_by_topic`, `get_user_credibility`, `get_topic_consensus` — V1.x.
- Vendor-specific direct SDKs in product code — forbidden per R4. All API calls go through the gateway.
- Authentication / authorization on MCP tools — V1 internal-only; V2 reopens.
