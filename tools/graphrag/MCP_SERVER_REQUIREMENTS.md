# GraphRAG MCP Server Requirements

## Server type
Start with local stdio MCP server.

## Security requirements
- Read-only retrieval tools by default.
- No arbitrary shell execution from model input.
- Validate file paths.
- Restrict access to repository root.
- Do not expose .env values.
- Log tool calls.
- Require approval for write tools if added later.

## Suggested project command

The final implementation should support a command like:

```bash
npm run graphrag:index
npm run graphrag:mcp
```

or:

```bash
python tools/graphrag/index.py
python tools/graphrag/mcp_server.py
```

## Claude Code project MCP config

A project-scoped `.mcp.json` should point to the GraphRAG MCP server.

Example:

```json
{
  "mcpServers": {
    "codebase-graphrag": {
      "command": "npm",
      "args": ["run", "graphrag:mcp"],
      "env": {}
    }
  }
}
```

## Required MCP tool behavior

Each tool must return:
- concise result
- file paths
- line ranges when available
- confidence
- why it is relevant
- linked docs/tests/code
