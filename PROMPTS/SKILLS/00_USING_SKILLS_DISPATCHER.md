# Skill: Using Skills Dispatcher

## Trigger
Use before any substantive response in this repository, including before asking clarifying questions.

## Purpose
Prevent the agent from improvising. Force it to select the correct workflow.

## Rule
Before acting, identify which skill(s) apply.

## Skill selection

- New idea, unclear request, creative/product/design task → Brainstorming
- Multi-step task with known requirements → Writing Plans
- Existing written plan → Executing Plans
- Feature or bugfix implementation → Test-Driven Development
- Bug, failing test, unexpected behavior → Systematic Debugging
- About to claim complete/fixed/passing → Verification Before Completion
- Major implementation completed → Requesting Code Review
- User or reviewer gives feedback → Receiving Code Review
- Independent parallel tasks → Dispatching Parallel Agents
- Starting isolated feature work → Using Git Worktrees
- Finishing a branch/workstream → Finishing Development Branch
- Docs needed → Documenting
- Deployment/release → Deploying
- Migration/data change → Migrating
- Performance issue → Optimizing
- Security-sensitive change → Auditing
- UI/UX exploration → Visual Companion

## Output format before work
State briefly:
- selected skill(s)
- why
- next action

## Hard rule
If a task matches a skill, follow that skill. Do not freestyle.
