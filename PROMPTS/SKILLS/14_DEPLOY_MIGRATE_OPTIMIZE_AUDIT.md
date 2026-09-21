# Skill: Deploy / Migrate / Optimize / Audit

## Deploy
Before deploy:
- verify env vars
- run tests
- check build
- document rollback
- validate monitoring/logging

## Migrate
Before data migration:
- document migration purpose
- backup/rollback or forward-fix strategy
- test migration
- update data.md
- require approval for destructive migrations

## Optimize
Before optimization:
- measure baseline
- identify bottleneck
- change one thing
- measure after
- avoid premature optimization

## Audit
For security-sensitive changes:
- validate inputs
- check authz/authn
- avoid secret leakage
- review dependencies
- add negative tests
