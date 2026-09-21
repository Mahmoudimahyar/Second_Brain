# State-of-the-Art Research Harness

## Trigger
Use before every major decision, including:
- product strategy
- architecture
- UI/UX pattern
- design system
- database design
- auth/security
- testing strategy
- GraphRAG/MCP architecture
- agent workflow
- library selection
- deployment
- data pipeline
- AI/LLM workflow

## Goal
Identify current best practices and state-of-the-art methods before committing to a decision.

## Required process
1. Define the research question.
2. Identify what decision depends on the research.
3. Search current official docs, reputable engineering blogs, high-quality open-source repos, and recent discussions when relevant.
4. Compare at least 2–4 viable approaches when possible.
5. Identify tradeoffs.
6. Identify risks and failure modes.
7. Make a recommendation.
8. Convert the recommendation into:
   - research-log entry
   - ADR if architectural
   - feature docs if product-facing
   - test requirements if behavior-facing
   - implementation rules if coding-facing

## Required output format

### Research question
...

### Why this matters
...

### Sources reviewed
...

### Options considered
...

### Recommendation
...

### Tradeoffs
...

### Risks
...

### Decision needed from user
...

### Docs to update
...

## Rules
- Do not research for show. Research must feed a decision.
- Do not blindly follow trends.
- Prefer official documentation and reputable open-source implementations.
- If sources disagree, document the disagreement.
- If the decision is reversible, say so.
- If the decision is hard to reverse, require explicit approval.
