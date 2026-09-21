# Changelog

All notable changes to SecBrain are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The project is pre-1.0 and is
versioned by **milestone** (V1.5 → V1.7) rather than SemVer; each milestone maps to a
feature packet under [`docs/05-features/`](docs/05-features/).

For what is actually wired and validated *right now*, the single source of truth is
[`docs/00-bootstrap/implementation-status.md`](docs/00-bootstrap/implementation-status.md).

## [Unreleased]

## [0.1.1] — 2026-09-21

The first public CI run was red within minutes of 0.1.0 — caught, reproduced, fixed.

### Fixed
- **CLI reference generator broke under Typer ≥ 0.26**, which vendors its own copy of click: a
  `TyperGroup` is no longer a `click.Group`, so an `isinstance` check failed and took the
  "reference pages are current" tests with it. The generator now walks the command tree by duck
  typing and produces byte-identical pages under both library generations. Root cause of the
  miss: the new tests had been run in a long-lived virtualenv, not a fresh one — CI did its job.

### Changed
- CI uses current major versions of the GitHub actions (Node 24 runtime).
- Dependabot only proposes a Python change when a release falls *outside* a declared range, and
  ignores the deliberate caps (`mcp < 2`, `crawl4ai 0.8.x`, `kuzu`), each with its reason.

## [0.1.0] — 2026-09-21 · first public release

The package version (`pyproject.toml`, `CITATION.cff`). Everything below this entry is the
milestone history that led to it.

### Added
- Project README with architecture diagram, results, and screenshots; Apache-2.0 `LICENSE` and
  a `NOTICE` that scopes out all data; CONTRIBUTING, SECURITY, CODE_OF_CONDUCT, CITATION.
- CI (pytest on Python 3.12 / 3.13 × Linux / Windows, pyflakes-level lint, doc-lint, web
  typecheck + unit tests), issue / PR templates, Dependabot, documentation index.
- `web`, `analysis` and `embeddings` extras; `evals/build_public_alias_gold.py`.
- **Two-minute quickstart** on fictional data (`examples/quickstart/`), replayed by a test.
- **User guide** (`docs/guide/`): concepts, architecture tour, adapters, MCP, configuration,
  FAQ — plus CLI and REST reference pages *generated from the code*
  (`python -m tools.docs.gen_reference`), with a test that fails when they go stale.

### Changed
- Public eval gold sets contain no third-party text (see `evals/README.md`).
- `cloud/` and `scripts/` no longer assume a particular checkout location.
- Architecture docs reconciled with `implementation-status.md`; pre-implementation docs
  carry dated *Historical* banners.
- Bootstrap-kit scaffolding moved out of the repository root into `docs/00-bootstrap/kit/`.

### Fixed
- `secbrain … --help` no longer crashes with `UnicodeEncodeError` on non-UTF-8 consoles
  (piped output / legacy Windows code pages).
- `.env.example` listed ~30 planned settings that no code read and omitted ~17 that code does
  read; it now matches the code exactly, enforced by a test.
- A clean `pip install -e ".[dev]"` now yields a passing suite: undeclared dependencies
  declared, `mcp` capped below 2.x, broken `graphrag-index` console script repointed.

## [V1.7 — Insights Pack] — 2026-06-22 → 2026-06-25

### Added
- **Offline, no-API-key agent skill pack** (`pack/`): deterministic analysis tools behind a
  stdio MCP server, a research-playbook skill, `uv` packaging, and cross-platform launchers.
- Offline assembly + scrub script that builds the pack from a corpus bundle.

### Fixed
- Pack boot failure: lazy `retrieval` package init, self-correcting vendoring, missing
  `rapidfuzz` dependency.

## [V1.7 — Research protocol] — 2026-06-21 → 2026-06-22

### Added
- **Enforced experimental protocol**: every research answer is a measured estimate with a
  sample size and confidence interval, or an explicit abstention (RP-1…RP-7).
- Classifier **calibration harness** with an honest low-reliability flag (RA-1).
- Reproducible labels and compound-question routing (RB-1, RB-2).
- Concept-grounded hybrid retrieval path, data-driven k-means topic granularity,
  cohort-scoped retrieval with junk filtering (MH-1…MH-3).

## [V1.7 — Evidence engine & provenance] — 2026-06-20 → 2026-06-21

### Added
- **Evidence Answer Engine** (`evidence_answer()` + `POST /api/v1/evidence`).
- **Evidence Dossier**: broad-then-filter recall layer and dossier engine
  (`POST /api/v1/dossier`) with always-counted stance percentages and L1-trusted adjudication.
- **Per-statistic auditable source sets** with drill-down to the exact posts (PV-1).
- Deterministic rendering + entailment guard for faithfulness (PV-2).
- Compositional query planner with true joins (PV-4); query-scoped sub-topic facets (PV-5).
- Pass-3 **signed-spectral clustering** (GAP-049); bitemporal L1 claim supersede caller (GAP-053).

### Fixed
- Out-of-domain over-answering: semantic relevance floor for L1 articles.
- Dossier stance determinism, abstain consistency, L1 de-duplication and snippet hygiene,
  with an end-to-end regression guard.

## [V1.7 — Full-corpus scale-out] — 2026-06-03 → 2026-06-13

### Added
- Cloud ingest kit (`cloud/`): AWS runbook and reproducible VM runners for Pass 3 / Pass 4
  over the full forum corpus, graph compaction, and batched SDN ingest.
- Predicate normalization, forum-consensus aggregation, and L1 anchoring in the resolution layer.
- **GraphRAG KB agent**: natural-language `ask` over graph + consensus + official data, wired
  into the CLI and API, with an ask-eval harness.
- Gated comment-level Pass 4 with measured cost analysis.
- Production crawl worker, `secbrain crawl` CLI, real PDF / XLSX extraction, and a
  20-domain official-source registry.
- Corpus bundle packaging: thread-complete raw store, graph export, MCP server, dataset card,
  and an explicit licensing / redistribution analysis.

### Changed
- Graph writes rebuilt for scale: `UNWIND` node upserts and bulk-`COPY` edge loads
  (fixes buffer-pool OOM on large graphs).
- Model gateway: request timeouts and retries, benchmark-driven per-task routing, env-overridable
  model IDs.

### Fixed
- L1 anchor clobbering during crawl merge; O(N·P) page scan; fresh-DB canonical index.
- Web graph routes now share the process-wide Kùzu handle.

## [V1.7 — SOTA re-architecture & wiring] — 2026-05-29 → 2026-05-31

Triggered by a self-audit that found capabilities marked "Locked" that were unit-tested but
never wired into a real entrypoint ([post-mortem](docs/00-bootstrap/why-drift-happened.md)).

### Added
- **Anti-drift gates**: four-state status vocabulary (`Decided → Built → Wired → Validated`),
  the Wiring Gate, and a **doc-lint guardrail** that fails when docs claim more than the code does.
- ADR-021…ADR-026 from a live-verified state-of-the-art review.
- Bitemporal `supersede_edge`; tier-as-prior + HALO temporal-decay ranking in `query_graph`;
  hybrid index (BM25 + HNSW + RRF); LLM judge + web verifier wired into the conflict resolver.
- Adversarial alias gold set; Qwen3-Embedding-0.6B blocker (embedder A/B); NuNER-Zero
  (NER bake-off); LLM-matcher fallback for the borderline entity-resolution band.
- Calibrated confidence cascade with a first-hop router (ADR-023).
- L1-anchored joint-confidence conflict resolver (ADR-026 bake-off → hybrid).
- L1 ground-truth ingest: schools, specialties, institutions, residency programs.
- Crash-resilient, checkpointed forum ingest with durable per-batch flush.

### Changed
- V1 core slice validated end-to-end on real data.
- Consensus no longer treats cluster size as truth (ADR-026).

### Fixed
- GPU decoupled from the ingest path (GAP-054); idempotent `upsert_edge` (`MERGE`, not `CREATE`).
- Alias precision: two-letter and embedded all-caps acronyms no longer match in forum text.

## [V1.6a — Website crawler] — 2026-05-27

### Added
- Crawl4AI adapter with `robots.txt` enforcement and a per-page cache; opt-in proxy fallback.
- Crawl registry with a blocked-domains list (SQLite).
- Staged website graph: L0 sitemap → L1 entity-tagged (512/64 chunking) → L2 full GraphRAG,
  with three-point budget enforcement.
- Prefect cron dispatcher; FastAPI routes under `/api/v1/ingest/web/*`; Next.js UI with
  Playwright + axe-core checks; six outbound MCP crawl tools.

## [V1.5] — 2026-05-27 (initial commit)

### Added
- Trust-tier knowledge-graph engine on Kùzu: five-pass extraction pipeline, entity
  resolution against canonical L1 entities, conflict resolution, HITL queue, audit log.
- External data-source connectors with user-declared tiers and cross-graph entity mapping
  (ADR-014, ADR-015); web-search conflict verification (ADR-016); feedback-loop prompt
  context (ADR-017, ADR-018).
- Next.js operations console (V1.5d redesign) over a FastAPI backend.
- Repo-level GraphRAG MCP context server (`tools/graphrag/`) for coding agents.
