# Final Claude Code Start Prompt

Read these files first:
- AGENTS.md
- CLAUDE.md
- PROMPTS/MASTER_BOOTSTRAP_PROMPT.md
- PROMPTS/SKILLS/00_USING_SKILLS_DISPATCHER.md
- PROMPTS/ROLE_HARNESSES/00_PROJECT_MODE_ROUTER.md
- docs/00-bootstrap/gates.md
- docs/03-research/continuous-research-policy.md
- tools/graphrag/IMPLEMENTATION_PLAN.md
- tools/graphrag/MCP_SERVER_REQUIREMENTS.md

Do not write application code yet.

Your first job is to bootstrap the repository correctly.

Follow this sequence:

1. Use the skill dispatcher.
2. Select project mode.
3. Interview me or ingest my uploaded docs.
4. Continuously identify gaps using the Gap Detection Harness.
5. Research state-of-the-art methods before every major decision.
6. Convert research into decisions, ADRs, docs, and test requirements.
7. Fill the required docs according to the project mode.
8. Create the site map/UI flows only if the project has UI.
9. Create marketing/sales docs only if the project mode or my explicit request requires them.
10. Identify every required environment variable and update .env.example.
11. Do not proceed to coding until gates pass.
12. Before app implementation, implement or connect the GraphRAG MCP context server unless I explicitly defer it.
13. Verify GraphRAG using tools/graphrag/verification-checklist.md.
14. For each feature, use TDD: failing test first, then implementation, then verification.
15. Before claiming completion, use Verification Before Completion and write a validation report.

Important:
If information is missing, ask focused questions.
If multiple options exist, use a decision menu.
If a best practice decision is needed, research current reputable sources and open-source references.
Do not guess silently.
