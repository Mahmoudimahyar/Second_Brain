# Skill Invocation Policy

The agent must choose and follow a named skill before acting.

## Why
Unstructured coding agents improvise, skip tests, over-read context, and claim completion without evidence.

## Required dispatcher
Use:
- PROMPTS/SKILLS/00_USING_SKILLS_DISPATCHER.md

## Skill log
Each meaningful task should record selected skills in:
- docs/00-bootstrap/skill-usage-log.md

## Completion rule
No task may be marked complete without:
- Verification Before Completion skill
- validation report
- evidence of tests or a clear note explaining what was not run
