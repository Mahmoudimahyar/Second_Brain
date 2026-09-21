# Non-Negotiables

> Rules the system **always** obeys. Violation of any of these blocks merge / blocks release.
>
> ⚠️ **Enforced vs Target (added 2026-05-29).** Some rules below are **enforced today**
> (e.g. #9 vendor-lock — verified in code) and some are **target invariants not yet
> enforced** because the capability isn't wired (e.g. #3 bitemporal supersede — GAP-053;
> #5 signed-graph step — GAP-049; #6 ranking-time citation guarantees depend on the unbuilt
> ranker — GAP-048). A rule being listed here means it is **mandatory once the capability is
> wired**, not that it is currently true. `docs/00-bootstrap/implementation-status.md` is the
> single source of truth for which are enforced now. Do not read this file as a status report.

## Architecture

1. **L1 is immutable.** No code path may UPDATE / DELETE a node with `source_tier = L1`. Any forum claim conflicting with L1 is flagged `Status: Invalidated_by_Official_Data` on the forum side, never L1.
2. **Every node and edge carries the full property convention.** `source_tier`, Wikidata `rank` (on claim edges), `references`, `qualifiers`, `t_valid_from`, `t_valid_to`, `t_ingest_from`, `t_ingest_to`, `created_utc`. Schema-locked from day one.
3. **Bitemporal correctness.** Every supersede operation atomically sets prior `t_ingest_to` + new `t_ingest_from` to the same instant. `query_graph(..., as_of=<past>)` must return the snapshot the graph believed valid at that time.
4. **Two GraphRAG deployments, distinct.** `tools/graphrag/` (repo retrieval for the coding agent) ≠ V1 product engine MCP. Conflating them is a bug.

## Data + sources

5. **Trust ladder respected in conflict resolution.** Order: L1-clash → temporal disambiguation → source-trust weighting → signed-graph community → web-verification trigger → HITL. Skipping a step is not allowed.
6. **Citations always.** Every retrieval result has non-empty `references`. Citation traceability ≥ 99% on the test set; CI gate failure if it drops below.
7. **Outlier preservation.** Contrarian claims are tagged `Status: Anomaly`, never deleted. `prescient_correct` is tracked for retroactive credibility.
8. **Source-aware credibility.** Reddit-rubric uses karma; SDN-rubric uses volume + longevity + on-topic ratio. Author IDs namespaced `reddit:<sub>:<author>` vs `sdn:<author>`. Cross-source identity reconciliation is V2.

## Models + vendors

9. **No vendor-locked code in the product engine.** `import anthropic` / `import openai` / `import google.genai` are forbidden outside `src/gateway/`. Enforced by `ruff` rule.
10. **All LLM calls go through `LLMClient` ABC.** No direct vendor SDK calls in product code.
11. **Prompt-cache `ttl: 3600` is mandatory.** Every cache-write call site explicitly sets `ttl: 3600`. Enforced by `lint_ttl_pinning.py`. (Anthropic silently changed the default to 5 min in March 2026.)
12. **Per-task model selection criteria are explicit and testable.** No "let me try Haiku" hidden in a prompt file. The per-task matrix in `tech-stack.md` is authoritative; switches are config + test, not code.
13. **LLM-as-judge restricted to same-tier same-year tie-breaks.** With three-vendor calibration (Sonnet 4.6 + Gemini 2.5 Flash + GPT-4.1-mini), ≥ 2/3 agreement required. Outside that window: HITL only.

## Discipline

14. **TDD discipline once implementation begins.** Failing test first → smallest correct change → targeted tests → broader tests → docs updated → Verification Before Completion. Per AGENTS.md.
15. **Repair budget respected.** ≤ 5 cycles unit/integration, ≤ 3 cycles E2E, ≤ 2 cycles full-suite. Past that, write a failure report.
16. **No silent invention of requirements.** Track assumptions in `assumptions.md`, unresolved questions in `unresolved-questions.md`, gaps in `gap-register.md`. Update on every round.
17. **Docs and tests are part of the implementation.** No PR is "done" without doc + test changes co-merged.
18. **GraphRAG retrieval before broad reads.** The coding agent uses `tools/graphrag/` MCP for context before reading raw files. Per CLAUDE.md.
19. **Verification Before Completion before claiming done.** Per AGENTS.md skill dispatcher. Validation report in `/.agent/reports/`.

## Security + privacy

20. **V1 internal-only.** No external network exposure of the product engine. V2 reopens security model.
21. **HITL approval for new node/edge types.** No ungoverned ontology sprawl. The system can *propose* new types via a HITL queue item; only Mahyar's commit makes it real.
22. **Audit log is the source of truth.** Every extraction, retrieval, HITL decision is audit-logged with sufficient detail to reconstruct state. Rebuilding the graph from `audit_log` + raw dumps must produce an identical graph (modulo non-deterministic clustering ordering).

## Cost

23. **Cost discipline is a design layer.** Every architecture decision weighs accuracy gain per dollar. **(Budget reconciliation, 2026-05-29:** GAP-007 closed the question as *"no hard budget cap; design for cost-efficiency."* The earlier "< $25 V1 slice / $80–300 full corpus" figures are **design targets / tripwires for alarm**, not merge-blocking caps. The merge-blocking rule is: cache-or-die (#24), cheap-cascade-first, and per-sweep cost telemetry — not a dollar ceiling.)
24. **Cache-or-die for reruns.** Content-addressable extraction cache before any API call. Warm sweep cache-hit ≥ 80%.

## Out-of-scope guardrails

25. **Marketing/sales/pricing/competitor docs for the project itself are skipped** unless Mahyar explicitly opts in. The downstream marketing-content-generation agent is a V2 product feature, not project marketing.
26. **The tool ingests data dumps; it does not crawl.** Crawling is a separate system. The tool's outbound MCP surface tells the crawler where the gaps are.
