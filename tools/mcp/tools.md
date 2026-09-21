# MCP Tool Specification — Repo MCP Server

> Full signatures + I/O schemas + examples. Implements the retrieval policy in `tools/graphrag/retrieval-policy.md`. Distinct from the V1 product engine MCP (`src/mcp/`).

## Tool catalog

All tools are **stdio MCP** in V1. Each input/output is a Pydantic model. Errors per `docs/06-api/error-codes.md`.

---

### `search_codebase`

Hybrid search across docs + code + tests + ADRs.

**Input:**
```
{
  "query": str,                                 # natural language; 1-500 chars
  "kind_filter": Optional[list[str]] = None,    # e.g., ["DocSection", "Function"]
  "limit": int = 20,                            # 1-100
  "snapshot_id": Optional[str] = None           # for time-travel
}
```

**Output:**
```
{
  "results": [
    {
      "node_id": str,
      "node_type": str,
      "snippet": str,                           # ≤ 300 chars
      "source_path": str,
      "line_range": Optional[[int, int]],
      "snapshot_id": str,
      "score": float,
      "match_explanation": str                  # short explanation of why this matched
    },
    ...
  ],
  "total_matches": int,                         # may exceed `limit`
  "snapshot_id": str,
  "warnings": list[str]                         # e.g., "snapshot 3 days stale"
}
```

**Example:**
- Input: `{"query": "where is the LLM gateway implemented"}`
- Output: top 20 mix of `Function`/`DocSection` results pointing to `src/gateway/api.py` + `docs/04-architecture/tech-stack.md#model-gateway`.

---

### `explain_feature`

Aggregated feature summary.

**Input:**
```
{
  "feature": str,                               # slug or canonical ID; e.g., "01-slice-trust-tier-canonicalize"
  "depth": int = 2,                             # graph traversal depth
  "max_per_section": int = 15
}
```

**Output:**
```
{
  "feature_id": str,
  "name": str,
  "status": str,
  "readme_summary": str,
  "requirements": [
    {"req_id": str, "title": str, "description": str, "kind": str}
  ],
  "acceptance_criteria": [{"ac_id": str, "description": str, "linked_req_ids": list[str]}],
  "code_files": [{"source_path": str, "loc": int}],
  "tests": [{"qualified_name": str, "linked_req_ids": list[str]}],
  "adrs": [{"adr_id": str, "title": str, "status": str, "decision_summary": str}],
  "known_issues": [{"ki_id": str, "severity": str, "description": str}],
  "snapshot_id": str
}
```

---

### `plan_change`

Suggest where to start for a goal.

**Input:**
```
{
  "request": str,                               # natural language goal
  "k_features": int = 3
}
```

**Output:**
```
{
  "selected_features": [
    {
      "feature_id": str,
      "name": str,
      "relevance_score": float,
      "summary": str,                           # 1-2 sentence
      "code_files": [str],                      # source paths
      "tests_to_run": [str],
      "risks": [str]                            # from KnownIssues
    }
  ],
  "relevant_adrs": [
    {"adr_id": str, "title": str, "constraint_summary": str}
  ],
  "suggested_implementation_order": [str],      # ordered list of step descriptions
  "snapshot_id": str
}
```

---

### `find_symbol`

Exact symbol lookup.

**Input:**
```
{
  "symbol": str,
  "kind_filter": Optional[list[str]] = None,    # e.g., ["Function", "Class"]
  "limit": int = 10
}
```

**Output:**
```
{
  "matches": [
    {
      "node_id": str,
      "node_type": str,
      "qualified_name": str,
      "source_path": str,
      "line_range": [int, int],
      "signature": Optional[str],
      "docstring": Optional[str],
      "parent_file": Optional[str],
      "match_kind": "exact" | "prefix" | "substring",
      "snapshot_id": str
    }
  ],
  "snapshot_id": str
}
```

---

### `get_feature_packet`

Full doc bundle for a feature.

**Input:**
```
{
  "feature": str                                # slug or canonical ID
}
```

**Output:**
```
{
  "feature_id": str,
  "documents": [
    {
      "source_path": str,
      "title": str,
      "content": str,                           # full content
      "section_count": int
    }
  ],
  "ordering": [str],                            # ordered list of source_paths (README first, etc.)
  "snapshot_id": str
}
```

---

### `get_related_tests`

Test traversal.

**Input:**
```
{
  "target": str,                                # canonical ID of Function / Class / Requirement / AC / Feature / CodeFile
  "max_depth": int = 2,
  "limit": int = 30
}
```

**Output:**
```
{
  "target_id": str,
  "target_type": str,
  "tests": [
    {
      "test_case_id": str,
      "qualified_name": str,
      "source_path": str,
      "markers": [str],
      "linked_req_ids": [str],
      "linked_ac_ids": [str],
      "traversal_path": [str]                   # which edges were followed
    }
  ],
  "snapshot_id": str
}
```

---

### `get_docs_for_code`

Reverse traversal: which docs cover this code?

**Input:**
```
{
  "file_or_symbol": str,                        # source path or canonical ID
  "limit": int = 20
}
```

**Output:**
```
{
  "target_id": str,
  "documents": [
    {
      "doc_section_id": str,
      "page_path": str,
      "anchor": str,
      "heading": str,
      "snippet": str,                           # ≤ 300 chars context
      "feature_id": Optional[str]
    }
  ],
  "snapshot_id": str
}
```

---

### `get_code_for_doc`

Forward traversal: which code is referenced by this doc?

**Input:**
```
{
  "doc_path": str,                              # repo-relative .md path
  "include_subsections": bool = True
}
```

**Output:**
```
{
  "doc_page_id": str,
  "code_references": [
    {
      "source_path": str,
      "line_range": Optional[[int, int]],
      "name": Optional[str],
      "kind": "CodeFile" | "Function" | "Class",
      "referenced_in_section": str              # heading
    }
  ],
  "snapshot_id": str
}
```

---

### `find_stale_docs`

Heuristic stale-doc detection.

**Input:**
```
{
  "changed_files": list[str],                   # repo-relative paths
  "days_threshold": int = 30                    # only flag if doc older than code by this many days
}
```

**Output:**
```
{
  "stale_candidates": [
    {
      "doc_section_id": str,
      "page_path": str,
      "anchor": str,
      "referenced_code_path": str,
      "code_last_modified": datetime,
      "doc_last_modified": datetime,
      "days_stale": int
    }
  ],
  "snapshot_id": str,
  "warnings": list[str]                         # e.g., "ADR files excluded by default"
}
```

---

### `validate_feature_docs`

Checklist for a feature packet.

**Input:**
```
{
  "feature": str
}
```

**Output:**
```
{
  "feature_id": str,
  "expected_files": [str],
  "present_files": [str],
  "missing_files": [str],
  "missing_sections": [
    {"file": str, "expected_section": str}
  ],
  "warnings": [str],
  "passes": bool,
  "snapshot_id": str
}
```

---

### `create_task_brief`

Compose a task brief.

**Input:**
```
{
  "goal": str,
  "save_path": Optional[str] = None             # if set, write to /.agent/tasks/<slug>.md
}
```

**Output:**
```
{
  "task_id": str,                               # generated slug
  "brief_markdown": str,                        # full brief
  "saved_to": Optional[str],
  "selected_features": [str],                   # feature IDs
  "estimated_files_touched": [str],
  "snapshot_id": str
}
```

---

## Cross-cutting

### Common error responses

Every tool may return one of:

```
{
  "error_code": str,         # per docs/06-api/error-codes.md
  "message": str,
  "context": dict,
  "retry_safe": bool
}
```

### Logging

Per `tools/graphrag/retrieval-policy.md`: every tool call → `tools/graphrag/logs/mcp.jsonl`.

### Versioning

Tool signatures are append-only across V1. Breaking changes require an ADR + a deprecation cycle.

## V2 reopens (preview)

- Streaming responses for long results.
- Write tools (e.g., `create_feature_packet` from a template) — gated on Mahyar approval.
- Cross-repo retrieval (when SecBrain has dependents).
- Pluggable retrieval backends (e.g., a Cohere reranker stage).
