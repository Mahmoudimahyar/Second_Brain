# Final Integrated AI-Agent Repository Bootstrap Kit

This is the fully merged kit. It includes:

- Original repo scaffold
- GStack-inspired specialist role harnesses
- Project-mode selection
- Superpowers-inspired mandatory skills
- Continuous state-of-the-art research and gap detection
- GraphRAG/MCP implementation requirements
- Claude Code setup instructions

## What this kit is for

Use this when starting a new codebase and you want the coding agent to:

- understand the project before coding
- ask focused questions
- research current best practices before major decisions
- identify gaps continuously
- fill structured docs
- avoid irrelevant marketing/sales docs when building a tool
- build or connect a GraphRAG/MCP context server
- use TDD
- validate UI in browser when relevant
- produce evidence before claiming completion

## Critical rule

Do not let the agent code application features immediately.

The correct sequence is:

1. Select skill.
2. Select project mode.
3. Interview user or ingest documents.
4. Identify gaps.
5. Research state-of-the-art methods.
6. Convert decisions into docs/ADRs/tests.
7. Fill required docs for the selected project mode.
8. Set up or explicitly defer GraphRAG/MCP.
9. Pass the gates.
10. Implement the first vertical slice with TDD and validation.

## First files Claude Code should read

- AGENTS.md
- CLAUDE.md
- PROMPTS/FINAL_CLAUDE_CODE_START_PROMPT.md
- PROMPTS/SKILLS/00_USING_SKILLS_DISPATCHER.md
- PROMPTS/ROLE_HARNESSES/00_PROJECT_MODE_ROUTER.md
- docs/00-bootstrap/gates.md
- docs/03-research/continuous-research-policy.md
- tools/graphrag/IMPLEMENTATION_PLAN.md
- tools/graphrag/MCP_SERVER_REQUIREMENTS.md

## Reality check

This kit defines the GraphRAG/MCP system and requires it, but does not magically contain a working GraphRAG server. Claude Code must either:

1. implement the GraphRAG MCP server as the first infrastructure task, or
2. connect to an existing working GraphRAG/MCP context server.

Do not allow the agent to claim GraphRAG is working until tools/graphrag/verification-checklist.md passes.
