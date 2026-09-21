# Gap Detection Harness

## Trigger
Use after every discovery round, research round, PRD update, architecture update, design update, UI-flow update, test-plan update, and before coding.

## Goal
Continuously identify missing information, weak assumptions, unclear decisions, and untested behavior.

## Gap categories
Check for gaps in:

1. Product intent
2. User/workflow
3. MVP scope
4. Out-of-scope boundaries
5. Data model
6. User roles/permissions
7. API contracts
8. UI flows
9. Error/loading/empty states
10. Testing strategy
11. Browser validation
12. Security/privacy
13. Observability
14. Deployment/DevEx
15. Environment variables
16. Library decisions
17. GraphRAG/MCP implementation
18. Documentation-code-test links
19. Performance constraints
20. Open-source/reference pattern research

## Required output

### Gaps found
| ID | Gap | Severity | Blocking? | Suggested resolution |
|---|---|---|---|---|

### Questions for user
Ask no more than 7 focused questions.

### Research needed
List research questions if gaps require current best practices.

### Docs to update
List exact files.

## Rules
- Do not proceed to coding with blocking gaps.
- Do not ask low-value questions.
- If a reasonable default exists, present it as a decision menu.
- If user says to skip a domain, mark it intentionally skipped.
