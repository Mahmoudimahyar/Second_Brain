# Retrieval Policy — Repo MCP Server

> Concrete algorithms per MCP tool. Pairs with `schema.md` (data) + `tools/mcp/tools.md` (signatures). Goal restated: **return the smallest sufficient context for the task.**

## Universal rules

- **Do not retrieve the entire docs folder.** Default `limit` = 20 results per tool unless caller overrides.
- **Do not retrieve the entire source tree.** Truncate code snippets to function-level.
- **Prefer linked docs over semantic guesses.** Graph edges beat embedding similarity when both are available.
- **Prefer exact symbol matches over vague similarity.** BM25 / exact-name lookups beat dense vectors for code symbols.
- **Returned results always include citations** (node IDs + file paths + line ranges where available).
- **Stale snapshots flagged** — every result includes a `snapshot_id`; the caller can detect drift.

## Per-tool algorithms

### `search_codebase(query, kind_filter=None, limit=20)`

Hybrid retrieval over docs + code + tests.

```
1. BM25 over node.name + node.title + node.qualified_name (for fast exact / prefix matches).
2. HNSW over DocSection chunk embeddings + Function docstring embeddings.
3. RRF fuse the two ranked lists (k=60 default).
4. Optionally filter by node_type in `kind_filter` (e.g., {"DocSection", "Function"}).
5. Truncate snippets to ≤ 300 chars per result.
6. Return list of {node_id, node_type, snippet, source_path, line_range?, snapshot_id, score}.
```

p95 latency target: < 200 ms on the V1 SecBrain corpus.

### `explain_feature(feature, depth=2)`

Aggregate the slice's full picture.

```
1. Find Feature node by slug.
2. Pull README content (DocSection).
3. List all Requirements + AcceptanceCriteria (FEATURE_HAS_REQUIREMENT, REQUIREMENT_HAS_ACCEPTANCE_CRITERION).
4. List linked Code: traverse FEATURE_IMPLEMENTED_BY (1-hop).
5. List linked Tests: TEST_COVERS_REQUIREMENT (≤ 2 hops via REQUIREMENT).
6. List relevant ADRs: ADR_DECIDES targeting any of the slice's Requirements / Code.
7. List KnownIssues: KNOWN_ISSUE_AFFECTS for any slice asset.
8. Compose into a single Markdown summary; cap each section at limit (e.g., 15 reqs, 10 code files, 20 tests).
```

p95 latency target: < 250 ms.

### `plan_change(request, k_features=3)`

Suggest where to start.

```
1. Embed `request` via BGE-small.
2. Hybrid search across DocSection chunks + Function docstrings (top-K results, K=15).
3. Cluster top results by Feature (count distinct Features in top results).
4. Pick top k_features Features by hit count.
5. For each Feature, run `explain_feature(slug, depth=1)` to get its essentials.
6. Add KnownIssues across all picked Features as a "watch out" section.
7. Add ADRs whose decision-summary embedding matches the request semantically (top 5).
8. Output: {features: [{summary, files, tests, risks}], adrs: [...], suggested_implementation_order: [...]}.
```

`suggested_implementation_order` is derived from Feature `priority` if present + edge density between Features.

### `find_symbol(symbol, kind_filter=None)`

Exact symbol lookup.

```
1. BM25 + exact-prefix match on Function.qualified_name + Class.qualified_name + Endpoint.path + ConfigKey.key + DatabaseTable.name.
2. If `kind_filter` is set, restrict to that node type.
3. For each match, include: qualified_name, source_path, line_range, parent_file, signature (for Function), docstring (truncated).
4. Sort by exact match first, then prefix, then substring.
5. Default limit: 10.
```

p95 latency target: < 50 ms.

### `get_feature_packet(feature)`

The full doc bundle.

```
1. Find Feature.
2. Traverse FEATURE_DOCUMENTED_BY → return every DocPage under the slice's directory.
3. For each DocPage, include full content.
4. Order: README → context → requirements → plan → api → data → state-machine → test-plan → decisions → known-issues → changelog (declared order; sortable by filename prefix if numeric).
```

p95 latency target: < 100 ms.

### `get_related_tests(target)`

Traverse to tests.

```
1. Identify `target` node type: Function / Class / Requirement / AcceptanceCriterion / Feature / CodeFile.
2. Traverse:
   - Function / Class → TEST_COVERS_FUNCTION (reverse) → TestCase
   - Requirement → TEST_COVERS_REQUIREMENT (reverse) → TestCase
   - AC → TEST_COVERS_ACCEPTANCE_CRITERION (reverse)
   - Feature → 2-hop: Feature → Requirement → TestCase
   - CodeFile → 2-hop: CodeFile → Function → TestCase
3. Dedupe.
4. Return list of TestCase with qualified_name + source_path + markers + linked req/ac IDs.
```

### `get_docs_for_code(file_or_symbol)`

Reverse traversal.

```
1. Identify input: CodeFile, Function, or Class.
2. Traverse:
   - DOC_SECTION_REFERENCES_CODE (reverse) → DocSection → DocPage
   - FEATURE_IMPLEMENTED_BY (reverse) → Feature → FEATURE_DOCUMENTED_BY → DocPage
3. Combine + dedupe + sort by (Feature, file order within the slice).
```

### `get_code_for_doc(doc_path)`

Forward traversal.

```
1. Find DocPage by source_path; expand to DocSections.
2. For each DocSection: traverse DOC_SECTION_REFERENCES_CODE → CodeFile / Function / Class.
3. Dedupe.
4. Return list with source_path + line_range + name.
```

### `find_stale_docs(changed_files)`

Timestamp-based heuristic.

```
1. For each path in `changed_files`:
   a. Find CodeFile node; get its last_modified_at.
   b. Traverse DOC_SECTION_REFERENCES_CODE (reverse) → DocSection.
   c. If DocSection.last_modified_at < CodeFile.last_modified_at → mark stale.
2. Return list of {doc_section_id, page_path, anchor, code_path, code_last_modified, doc_last_modified, days_stale}.
3. Sort by days_stale descending.
```

Caveat: heuristic only. Some docs are intentionally "set and forget" (e.g., ADRs). The agent should treat these as suggestions, not certainties.

### `validate_feature_docs(feature)`

Checklist runner.

```
1. Find Feature.
2. For each expected file under docs/05-features/<slug>/:
   - README, requirements, context, plan, api, data, state-machine, test-plan, decisions, known-issues, changelog
   → assert presence; if missing, emit a warning.
3. For each present file, run required-sections check:
   - README must contain "## Acceptance criteria" or equivalent
   - requirements.md must have FR-1..FR-N + NFR-1..NFR-N
   - test-plan.md must have the AC → test mapping table
4. Return {feature_slug, expected_files: [...], missing_files: [...], missing_sections: [...], warnings: [...]}.
```

### `create_task_brief(goal)`

Compose a task brief.

```
1. Run plan_change(goal, k_features=2).
2. For each selected Feature:
   - Pull requirements relevant to the goal (semantic match on goal vs requirement description).
   - Pull related tests for those requirements.
   - Pull ADRs that affect this Feature.
   - Pull KnownIssues for this Feature.
3. Compose a Markdown brief with sections:
   - Goal (caller-provided)
   - Relevant Features (1-2)
   - Key requirements (3-8)
   - Files to touch (from FEATURE_IMPLEMENTED_BY)
   - Tests to write/run (from get_related_tests)
   - ADRs to honor (top 3)
   - Watch out for (KnownIssues, top 3)
   - Suggested order (1, 2, 3 steps)
4. Save under `/.agent/tasks/<slug>.md` if `--save` flag.
```

## Embedding chunking

- **DocSection text**: split by paragraph; chunk size cap ≈ 800 chars; overlap 100 chars at section boundaries.
- **Function**: embed `(signature + docstring + first 5 lines of body)` as a single chunk; full body retrieved on demand.
- **Class**: embed `(class signature + class docstring + method names list)`.
- **ADR**: embed `(title + decision summary + first paragraph of consequences)`.

## Ranking weights (for fusion / final ordering)

Default weight model when results from multiple sources compete:

```
final_score = 0.4 × bm25_score + 0.4 × hnsw_score + 0.2 × graph_proximity_boost
```

Graph-proximity boost: results connected by edges to the query's "target" entity (e.g., a Feature the query mentions) get a small uplift.

Tune at implementation time; this is a starting point.

## Truncation rules

- DocSection bodies: full body if ≤ 1500 chars; else first 1500 + "...".
- Function bodies: signature + docstring + "(N lines)"; full body on explicit `get_code_for_doc` request.
- Lists in `explain_feature` / `create_task_brief`: capped per section (15 requirements / 10 code files / 20 tests / 5 ADRs).

## Caching

- BM25 + HNSW indexes live in the graph DB / sidecar; no separate cache.
- For `explain_feature` results, cache by `(feature_slug, snapshot_id)` for 5 minutes (in-memory; not persisted). Invalidated on next `index.py` run.

## Error semantics

Per `docs/04-architecture/error-handling.md` + `docs/06-api/error-codes.md`. Specific to graphrag tools:

- `RETRIEVAL_NODE_NOT_FOUND` — feature / symbol / doc path not found.
- `RETRIEVAL_TIMEOUT` — exceeded latency budget (rare; index small).
- `SCHEMA_VALIDATION_FAILED` — internal: tool output didn't match its declared schema.
- `SNAPSHOT_STALE` — index hasn't been run since last commit; tool returns results + warning.

## Observability

Every tool call writes to `tools/graphrag/logs/mcp.jsonl`:

```json
{
  "ts": "2026-MM-DDTHH:MM:SSZ",
  "tool": "search_codebase",
  "args_hash": "sha256:...",
  "result_count": 12,
  "latency_ms": 87,
  "snapshot_id": "...",
  "error_code": null
}
```

Aggregations (V1 informal; Mahyar reviews):
- Per-tool call frequency + latency p95.
- Cache hit rate (when caching added).
- Snapshot staleness warnings.
