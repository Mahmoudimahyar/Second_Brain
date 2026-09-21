# Skill: Using Git Worktrees / Isolated Workspaces

## Trigger
Use before substantial feature work, parallel workstreams, risky refactors, or experiments.

## Goal
Protect the main workspace from messy agent edits.

## Process
1. Check current git status.
2. Do not overwrite user changes.
3. Create branch/worktree if appropriate.
4. Define allowed edit paths.
5. Run baseline tests if feasible.
6. Work only inside the isolated branch/worktree.
7. Clean up after branch completion.

## Rule
Never destroy user changes.
