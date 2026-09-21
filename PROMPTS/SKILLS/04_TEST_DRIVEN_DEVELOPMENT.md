# Skill: Test-Driven Development

## Trigger
Use for any feature or bugfix implementation.

## Iron rule
No production code before a failing test, unless the task is pure documentation or configuration with no executable behavior.

## Process
1. Identify behavior to test.
2. Write failing test.
3. Run test and confirm it fails for the right reason.
4. Implement minimal code.
5. Run test and confirm it passes.
6. Refactor only if tests stay green.
7. Add integration/E2E tests as required by test plan.
8. Update docs.

## If the agent wrote production code first
Stop. Add the missing test. If necessary, revert or rewrite the implementation around the test.
