# Decisions — V1.5a

> Slice-local decisions that extend (don't override) the V1 ADRs. Authoritative cross-cutting decisions live in `docs/11-decisions/ADR-*`.

| ID | Decision | Rationale | Status |
|---|---|---|---|
| D-1.5a-1 | DataSource Protocol wraps existing V1 SourceAdapter | Minimal-risk refactor; V1 callers unchanged | Locked V1.5-R1 |
| D-1.5a-2 | Engine extras optional: `pip install secbrain[postgres,mysql,neo4j]` | Keep core install slim; testcontainers in dev only | Locked |
| D-1.5a-3 | Postgres driver = `psycopg[binary]` 3.x + `psycopg_pool` | Modern + binary-bundled (no compile on Mahyar's Win 11); pool for concurrent discovery + pull | Locked |
| D-1.5a-4 | MySQL driver = `mysql-connector-python` | Official; permissive license | Locked |
| D-1.5a-5 | Neo4j driver = official `neo4j` Python driver | Bolt; first-party | Locked |
| D-1.5a-6 | Schema discovery samples 100 rows per table by default | Enough signal for embedding-based suggestion; configurable down to 0 (no sampling) | Locked |
| D-1.5a-7 | MappingSuggester confidence thresholds match V1 alias resolution (0.75/0.90) | Consistent HITL routing across the system | Locked V1.5-R1 |
| D-1.5a-8 | SAME_AS edges stored single-edge canonical-ordered by node-id, auto-mirrored on read | Avoids 2x storage; symmetric semantics preserved | Locked ADR-015 |
| D-1.5a-9 | Re-pull cursor fallback chain: `updated_at` → `created_at` → `pk` | Most real-world tables have one of the three | Locked |
| D-1.5a-10 | Tier-change forces full re-ingest (closes prior `t_ingest_to`, opens new) | No silent re-writes; bitemporal preserves history | Locked ADR-014 |
| D-1.5a-11 | Tavily-only stub in V1.5a is OK (V1.5c implements actual WebVerificationAgent) | V1.5a is headless; web-verify is a V1.5c concern | Locked |
| D-1.5a-12 | Plaintext `.env` for credentials with UI banner | V1.5-R1 user choice; V2 reopens via OS keychain ADR | Knowingly accepted V1.5-R1 |
