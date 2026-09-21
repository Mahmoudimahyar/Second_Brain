# Skill: Dispatching Parallel Agents

## Trigger
Use when two or more tasks are independent and can be completed without shared mutable state.

## Requirements
For each workstream define:
- goal
- allowed edit paths
- forbidden paths
- inputs
- outputs
- tests
- merge order
- collision risks

## Rule
Do not parallelize tasks that touch the same files, shared contracts, database schema, or unstable APIs.
