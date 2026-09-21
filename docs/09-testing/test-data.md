# Test Data

> Catalog of fixtures, gold sets, builders, and mocking rules. Source of truth for what `tests/fixtures/`, `evals/gold/`, and `tests/builders/` contain.

## Categories

| Category | Location | Purpose | Determinism |
|---|---|---|---|
| Synthetic unit fixtures | `tests/fixtures/synthetic/` | Stable inputs for unit + integration | Hand-crafted; version-controlled |
| Real-data subsamples | `tests/fixtures/real/` | E2E on actual forum/Excel data | Deterministic seed-based subsample of `External Data\` |
| Recorded vendor responses | `tests/fixtures/vcr/` | Cross-vendor switch + Stage-3 integration | Re-recorded when prompts/schemas change |
| Builders | `tests/builders/` | Programmatic test-object construction | Pure Python; no external state |
| Gold sets (eval) | `evals/gold/` | F1 / precision / recall targets | Hand-labeled; PR review required for additions |

## Synthetic unit fixtures (catalog)

| File | Records | Purpose |
|---|---:|---|
| `synthetic_threads.jsonl` | 100 | Common alias variations, conflict patterns, edge cases. Used by most unit + integration tests. |
| `synthetic_l1_mini.sqlite` | 5 schools / 50 metrics / 10 programs | Frozen mini-ADEA. L1 adapter unit tests + ER blocking-index seed. |
| `synthetic_hitl_items.jsonl` | 30 | Borderline / conflict / new-type-proposal / judge-disagreement exemplars. |
| `synthetic_adea_r2_mini.xlsx` | 5 sheets × ~20 rows | Mimics ADEA Report 2 schema; no real data. L1 adapter unit tests. |
| `synthetic_reddit_posts.jsonl` | 50 | Reddit-shape posts with full karma/score fields. |
| `synthetic_reddit_comments.jsonl` | 150 | Reddit-shape comments with `parent_id`/`link_id` for thread reconstruction. |
| `synthetic_sdn_threads.jsonl` | 20 | SDN-shape thread metadata + 5-10 posts each. No score field. |
| `synthetic_conflicts.jsonl` | 30 | L1-clash + temporal-split + same-year-trust + anomaly + HITL-pending exemplars (one per conflict-resolution path). |
| `synthetic_bitemporal_scenarios.jsonl` | 15 | Re-ingest sequences for "as of past date" tests. |

## Real-data subsamples

Built via deterministic seed from `External Data\`. Sampling scripts in `tests/fixtures/build_real_subsample.py`:

| File | Records | Source | Seed | Purpose |
|---|---:|---|---:|---|
| `real_r_dentalschool_100.jsonl` | 100 threads (post + comments reconstructed) | `External Data\Forum\Reddit\r_DentalSchool_*.jsonl` | 42 | E2E slice tests |
| `real_sdn_predental_100.jsonl` | 100 SDN Pre-Dental threads with posts | filtered from `External Data\Forum\sdn_llm\` | 42 | Schema-cross-validation tests (no-karma path) |
| `real_adea_r2_2024_25.xlsx` | (link to actual file) | `External Data\Official Dental School Data\Report 2_*\SDE2_2024-25.xlsx` | n/a | Integration test for L1 adapter |
| `real_adea_r2_2023_24.xlsx` | (link) | same dir | n/a | Year-on-year temporal tests |

**Build command**: `python tests/fixtures/build_real_subsample.py --seed 42`. Reproducible; the resulting fixtures are *not* committed to git (regenerated on demand). The build script is committed.

## Recorded vendor responses (VCR-style)

| Directory | Vendor | Coverage |
|---|---|---|
| `vcr/anthropic/stage3_sentiment/` | Anthropic | 50 Stage-3 sentiment calls, varied inputs |
| `vcr/anthropic/stage3_interview_q/` | Anthropic | 30 Stage-3 interview-Q-harvest calls |
| `vcr/openai/judge/` | OpenAI | Cross-vendor judge tie-break exemplars (V1.x activation) |
| `vcr/gemini/judge/` | Google | Cross-vendor judge tie-break exemplars |
| `vcr/anthropic/cache_hit/` | Anthropic | Same-input replays demonstrating cache hits |
| `vcr/anthropic/rate_limit/` | Anthropic | 429 responses for retry-logic tests |
| `vcr/anthropic/5xx/` | Anthropic | 500/503 responses for fallback-chain tests |

Recording protocol:
1. Set `RECORD_VCR=1` in env.
2. Run the integration test; live calls are recorded to the `vcr/` directory.
3. Commit the recordings.
4. Mahyar reviews to ensure no secrets / no PII leaked into responses.

Re-record when:
- Prompt template version bumps.
- Schema changes.
- Vendor API version changes.

## Builders

| File | Builders provided |
|---|---|
| `tests/builders/nodes.py` | `make_school()`, `make_program()`, `make_post()`, `make_comment()`, `make_user()`, `make_claim()`, ... |
| `tests/builders/edges.py` | `make_mentions_school_edge()`, `make_supports_edge()`, `make_authored_edge()`, ... |
| `tests/builders/dumps.py` | `make_l1_dump_manifest()`, `make_l5_reddit_dump_manifest()`, ... |
| `tests/builders/hitl.py` | `make_hitl_item()`, `make_decision()` |
| `tests/builders/audit.py` | `make_audit_extraction_row()`, `make_audit_retrieval_row()`, ... |
| `tests/builders/conflict.py` | `make_l1_clash_scenario()`, `make_temporal_split_scenario()`, ... |

Builder rules:
- All builders use sensible defaults; required arguments are the *minimum* a caller needs to express intent.
- Builders return immutable `dataclass` / Pydantic instances.
- No hidden global state — each call returns a fresh object.
- Builders include valid bitemporal 4-tuples by default; tests that need otherwise override explicitly.

## Gold sets (eval)

| File | Examples | Purpose | Target |
|---|---:|---|---|
| `evals/gold/alias_resolution_v1_200.jsonl` | 200 | School/program mentions → canonical IDs | F1 ≥ 0.92 |
| `evals/gold/sentiment_v1_100.jsonl` | 100 | Sentiment polarity on r/DentalSchool excerpts | F1 ≥ 0.85 |
| `evals/gold/interview_q_v1_50.jsonl` | 50 | Span detection + structuring of reported interview questions | Precision ≥ 0.90 |
| `evals/gold/conflict_resolution_v1_30.jsonl` | 30 | End-to-end conflict-resolution outcomes | Accuracy ≥ 0.90 |

Each gold-set row format:

```jsonl
{"id": "<unique>", "input": <task-specific>, "label": <ground truth>, "rationale": "<short why>", "labeled_by": "mahyar", "labeled_at": "2026-MM-DD", "version": 1}
```

**Labeling protocol** (per SD-016):
- Mahyar (or contracted dental-admissions expert in V1.x) labels.
- Borderline calls get a `rationale`.
- Disagreements among labelers (when contracted reviewer comes in) → escalate to discussion, then re-label.
- A `tools/eval_label_review.py` script samples 5% of labels for review at every gold-set update.

## Mocking rules (cross-references `testing-strategy.md`)

- **At the gateway boundary, not deeper.** Tests for `src/conflict/` mock `LLMClient`, not `anthropic.messages.create()`.
- **Time** → `freezegun`.
- **Random** → seed via `random.seed(42)` or `numpy.random.seed(42)`.
- **HTTP** → `respx` at the httpx layer.
- **stdlib** → don't mock.
- **structlog** → use `caplog`; assert on actual records.
- **MCP server** → use `mcp` SDK's test mode.

## Cleanup / hygiene

- Temp dirs for SQLite / graph DB instances created per test via pytest fixture with explicit teardown.
- `data/sqlite/test_*.db` cleaned at session start.
- No state leaks between tests — each test owns its instances.

## What's NOT in test data

- Real API keys (in `.env`; never committed).
- Mahyar's personal data.
- Anything from `External Data\` itself (those files are large + license-sensitive; subsamples are computed on demand).
- Production audit logs.
