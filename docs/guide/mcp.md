# Use it from an AI agent (MCP)

SecBrain ships two [Model Context Protocol](https://modelcontextprotocol.io) servers, both over
stdio. Any MCP-capable client (Claude Code, Claude Desktop, Cursor, your own agent) can use them.

| Server | Command | Gives an agent… |
|---|---|---|
| **Engine** | `secbrain-mcp` | tier-aware, time-aware, cited access to *your knowledge graph* |
| **Repo context** | `graphrag-mcp` | a docs ↔ code ↔ tests graph of *this repository*, for coding agents |

## Configure

The repository's [`.mcp.json`](../../.mcp.json) registers both for clients that read it:

```json
{
  "mcpServers": {
    "secbrain-v1": {
      "command": "python",
      "args": ["-m", "src.retrieval.mcp_server"],
      "env": { "SECBRAIN_DATA_DIR": "./data" }
    },
    "secbrain-graphrag": {
      "command": "python",
      "args": ["-m", "tools.graphrag.mcp_server"],
      "env": { "GRAPHRAG_DB_PATH": "./data/graph/repo.db" }
    }
  }
}
```

Use the Python interpreter of the environment where you ran `pip install -e .`. Point
`SECBRAIN_DATA_DIR` at the data directory you ingested into — for the quickstart, `./demo/data`.

## Engine server — `secbrain-mcp`

| Tool | Purpose |
|---|---|
| `query_graph` | The main entry point. `query`, plus optional `source_tier_min` (`L1`…`L5`), `traversal_depth` (default 2), `limit` (default 20), `as_of` (ISO-8601 — reconstruct what the graph believed at that moment), `include_anomalies`. Every returned record carries its tier and citation references. |
| `get_canonical_entity` | Snap a free-text alias to its canonical L1 entity; returns id, name, match confidence and known aliases — or an explicit no-match. |
| `stats` | Node and edge counts. |
| `connect_data_source` · `discover_schema` · `suggest_mapping` · `commit_mapping` · `pull_delta` · `list_connectors` · `disconnect_data_source` | Drive an external-database connector end to end: connect with a declared tier, inspect the schema, get table-to-graph mapping suggestions, commit a mapping, pull changes. |

A typical agent loop: resolve the entity → `query_graph` with `source_tier_min="L1"` for the
authoritative facts → `query_graph` again without the floor to see what the community says →
answer with both, citing the `refs`.

> Six crawl-management tools (`register_crawl_domain`, `trigger_crawl_now`, …) exist in
> `src/integrations/mcp_crawl_tools.py` with tests, but are **not yet registered** in this
> server. By the project's own rule they are *Built*, not *Wired*, so they are not advertised as
> available.

## Repo-context server — `graphrag-mcp`

Build the index first (about half a minute, no keys):

```bash
graphrag-index --full
graphrag-verify          # optional: runs the verification checklist
```

| Tool | Purpose |
|---|---|
| `search_codebase` | Hybrid search across docs, code, tests, ADRs and known issues. |
| `find_symbol` | Exact / prefix / substring lookup of functions, classes, files, config keys, test cases. |
| `explain_feature` | One aggregated view of a feature: summary, requirements, acceptance criteria, code, tests, ADRs, known issues. |
| `get_feature_packet` | Every document of a feature packet, in canonical order. |
| `get_related_tests` | Tests that cover a requirement, acceptance criterion, feature, function or file. |
| `get_docs_for_code` / `get_code_for_doc` | Traverse the doc ↔ code links in either direction. |
| `find_stale_docs` | Doc sections older than the code they reference. |
| `validate_feature_packet` | Check a packet has its required documents. |
| `plan_change` / `create_task_brief` | Suggest where to start for a goal, and turn that into a task brief. |

This server is why an agent working in the repo can ask *"which tests cover this function?"*
instead of reading the tree — and it is how this project keeps agent context small. Design notes:
[`tools/graphrag/architecture.md`](../../tools/graphrag/architecture.md).

## Security

Both servers are local stdio processes: no network listener, no authentication layer. The
repo-context server never returns `.env`, key or certificate file contents and logs each call.
Treat any agent you connect as having read access to the whole graph. See
[`mcp-security.md`](../12-security/mcp-security.md).
