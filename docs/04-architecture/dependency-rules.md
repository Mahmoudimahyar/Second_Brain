# Dependency Rules

> Python project. Multi-vendor LLM + graph DB + MCP stack. Rules below supersede the generic boilerplate originally in this file.

## Principles

1. **Every dependency justifies its weight.** Before adding any package, write a line in `library-decision-matrix.md` explaining why the existing stack can't do it.
2. **Pin minimum versions, allow patches.** `>=` for compatibility floors, no `==` pins outside lockfile. Lock via `uv` / `poetry` / `pip-tools` (lockfile pick made at implementation start).
3. **No vendor lock-in in product code.** All LLM SDKs (`anthropic`, `openai`, `google-genai`) are dependencies of `src/gateway/` ONLY. Enforced by `ruff` import-ban rule.
4. **No circular imports.** Tested in `tests/test_import_graph.py`.
5. **Cross-module imports go through public APIs.** See `module-boundaries.md`.

## Categories of dependencies

### Tier 1 — Core stack (locked, V1 baseline)

These are picked + version-pinned in `tech-stack.md`. PR to change any of them requires an ADR or ADR-revision.

- **Runtime**: `python>=3.12`.
- **Data**: `pandas>=2.2`, `openpyxl>=3.1`, `orjson>=3.10`, `zstandard>=0.22`, `pyarrow>=16`.
- **NLP/ML local**: `spacy>=3.7`, `gliner>=0.2` (GLiNER2), `sentence-transformers>=3.0` (BGE-small), `xgrammar>=0.1` (local constrained decoding), `transformers>=4.45` (DITTO/DistilBERT loader).
- **LLM gateway**: `litellm` (SDK mode), `anthropic`, `openai`, `google-genai` — direct vendor SDKs only inside `src/gateway/`.
- **Prompt programming**: `baml-py>=0.222`. DSPy 3.0 deferred to V1.x.
- **Validation**: `pydantic>=2.5`.
- **MCP**: `mcp` (Anthropic SDK) for both `tools/graphrag/` and V1 product engine MCP.
- **Graph DB driver**: pinned by ADR-001 bake-off winner — `kuzu`/`ladybugdb` OR `graphiti-core` + `neo4j` OR `psycopg[binary]` + `pgvector` + `apache-age`. Only one of the three goes into the lockfile.
- **Vector / FTS**: `tantivy` (if Tantivy wins per ADR-002) or Postgres FTS via `psycopg`.
- **Observability**: `structlog>=24`, `langfuse>=2.x`.
- **CLI**: `typer>=0.12`, `rich>=13`.
- **HTTP**: `httpx>=0.27`.
- **Test stack**: `pytest>=8`, `pytest-asyncio>=0.23`, `pytest-cov>=5`, `hypothesis>=6.100`, `freezegun>=1.5`, `respx>=0.21`.
- **Lint/type**: `ruff>=0.6`, `mypy>=1.11`.

### Tier 2 — Tools / dev-only

Allowed without ADR if dev-only and clearly justified. Examples: `ipython`, `jupyter`, `tqdm`, `python-dotenv`. Listed in `pyproject.toml` `[project.optional-dependencies.dev]`.

### Tier 3 — Experimental / scratch

NEVER pulled into `src/`. Goes in `experiments/` (gitignored as needed). If an experiment graduates, it goes through the ADR flow.

## Approval-required changes

Per AGENTS.md "Human approval required":
- Adding any new LLM vendor SDK (currently `anthropic`, `openai`, `google-genai` — adding a 4th is approval-required).
- Adding a new graph-DB driver beyond the ADR-001 winner (would imply a 2nd back-end pluggability layer).
- Adding any package that bundles its own LLM call (e.g., `openai`-using libraries that aren't vendor SDKs themselves) — must verify it goes through our gateway, not direct.
- Removing or downgrading a Tier-1 package.
- Adding any package with non-permissive license (anything not MIT/Apache-2.0/BSD/PostgreSQL by default).

## Banned / discouraged

- **`requests`** — use `httpx` for sync + async parity.
- **`pickle` over the wire** — explicitly forbidden in MCP / API surfaces.
- **`subprocess` in product code** — only allowed in `tools/` scripts.
- **`eval()`, `exec()`** — absolutely forbidden.
- **Heavy ML frameworks for inference** (`torch`+`transformers` are fine but only for the local NER/embedding/reranker path; full-fat `pytorch-lightning`/`accelerate` would need ADR-justification).
- **Web framework dependencies in V1** (`fastapi`, `flask`, `django`) — V1 ships CLI + MCP stdio only. V2 reconsiders.
- **`langchain`** — explicit reject. We're building the chain ourselves via the gateway + BAML; langchain's abstractions duplicate ours, churn fast, and obscure cost telemetry.

## Version-update policy

- **Security patches**: applied within 1 week of vendor advisory. Skip the ADR for these.
- **Minor versions**: applied at the next milestone (release cut), with smoke tests.
- **Major versions**: ADR required. Especially for `litellm`, `anthropic`, `pydantic`, graph-DB driver, `mcp`.
- **GLiNER2 / XGrammar / BAML**: monitor monthly for breaking changes during V1.

## License audit

V1 internal-only relaxes the license bar slightly but we still audit at every dependency addition:

| Acceptable | Borderline (approval required) | Reject |
|---|---|---|
| MIT, Apache-2.0, BSD, PostgreSQL, ISC | LGPL (case-by-case), MPL-2.0 (case-by-case) | GPL-3.0+, AGPL, BSL with restrictive clauses, no-license-stated |

Neo4j Community is GPLv3 — already noted in `tech-stack.md` as a known trade-off (V2 may force a swap if we distribute the engine).

## Discovery: how do we know what we depend on?

- `uv pip compile` / `poetry export` produces a frozen lockfile.
- `pip-licenses` runs in CI and fails on a non-allowlist license.
- `pip-audit` runs weekly for CVE alerts.

## Testing dependency changes

Any PR that touches `pyproject.toml`:
1. Lockfile regenerated.
2. Full test suite runs.
3. `pip-licenses` audit clean.
4. PR description states the justification + the alternative considered.
5. If approval-required: explicit Mahyar approval on the PR before merge.
