# Configuration

SecBrain is configured through environment variables, loaded from `.env` in the working
directory (or `--env-file`). **Nothing is required** to install, run the tests, or follow the
[quickstart](../../examples/quickstart/README.md). Copy [`.env.example`](../../.env.example) and
fill in only what you use.

This page lists every variable the code actually reads. An earlier `.env.example` also listed
planned settings that nothing consumed; they were removed, and this page is checked against the
code the same way.

## LLM vendors

Needed only for the LLM passes (`extract`, cluster summaries, `resolve`, `ask`, the evidence
engines). All traffic goes through `src/gateway/`; set keys for the vendors you want used, and
the gateway routes around whatever is missing.

| Variable | Used for |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic models — nuanced extraction, the hardest tier, one judge seat |
| `OPENAI_API_KEY` | OpenAI models — one judge seat, fallback |
| `GOOGLE_API_KEY`, `GEMINI_API_KEY` | Gemini. The availability check reads the first, the adapter reads the second: **set both to the same value** |
| `TOGETHER_API_KEY` | Open-weights models through Together's OpenAI-compatible endpoint (bulk extraction in the reference deployment) |
| `XAI_API_KEY`, `NVIDIA_API_KEY` | Optional OpenAI-compatible providers |
| `TAVILY_API_KEY` | Web verification of contested claims |

The three-vendor judge is only constructed when **all three** families are available
(Anthropic, OpenAI, Google); with fewer, same-tier ties escalate to human review instead. A judge
never scores a claim extracted by its own family.

### Routing switches

| Variable | Default | Effect |
|---|---|---|
| `SECBRAIN_PLAN_B` | unset | `1` routes bulk extraction to open-weights models |
| `SECBRAIN_PLANB_VARIANT` | `gemini` | `gemini` or `grok` — which family handles sentiment and question extraction under Plan B |
| `SECBRAIN_CONFLICT_PROVIDER` | `together` | Provider for conflict-candidate extraction |
| `SECBRAIN_TG_TIMEOUT` | `90` | Request timeout (seconds) for Together |
| `SECBRAIN_CASCADE` | unset | `1` enables the calibrated confidence cascade with a learned first-hop router ([ADR-023](../11-decisions/ADR-023-calibrated-cascade-and-router.md)) |
| `SECBRAIN_JOINT_RESOLVER` | unset | `1` enables the L1-anchored joint-confidence conflict resolver ([ADR-026](../11-decisions/ADR-026-truth-discovery-evaluation-spike.md)) |
| `SECBRAIN_OFFLINE` | unset | `1` forbids network calls from the conflict and team paths (used by tests) |
| `SECBRAIN_MODEL_*`, `SECBRAIN_TG_MODEL` | see `src/gateway/api.py` | Override the model id per task without touching code |

## Storage

| Variable | Default | Effect |
|---|---|---|
| `SECBRAIN_DATA_DIR` | `data` | Where the SQLite store, the Kùzu graph and raw dumps live. Same as the CLI's `--data-dir`; the API and MCP server read it from the environment. |
| `SECBRAIN_KUZU_BUFFER_POOL_BYTES` | unset | Caps Kùzu's buffer pool. **Unset means roughly 80 % of system RAM** — fine on a server, unpleasant on a laptop with a large graph. `4294967296` (4 GiB) is a sensible workstation value. |
| `SECBRAIN_BUNDLE` | unset | Directory of a built corpus bundle (document store, embedding shards, article index). Enables `/api/v1/dossier`; without it that route answers `503`. |
| `GRAPHRAG_DB_PATH` | `./data/graph/repo.db` | Index file for the repo-context MCP server |

## Website crawler

| Variable | Default | Effect |
|---|---|---|
| `CRAWL4AI_USER_AGENT` | — | **Required to crawl.** An honest user-agent with a way to contact you. The adapter refuses to start when it is empty. |
| `SCRAPINGBEE_API_KEY` | unset | Opt-in proxy fallback for sites that wrongly block polite crawlers. Off unless enabled per domain. |
| `TRAFILATURA_SUBPROCESS_BIN` | `trafilatura` | Main-content extraction fallback, run as a subprocess |

Crawler behaviour that is *not* configurable, on purpose: `robots.txt` is always honoured,
crawl-delay is respected (clamped to 0.5–10 s), and forum and social-media domains are blocked
from the crawl path.

## Human-in-the-loop

| Variable | Default | Effect |
|---|---|---|
| `SECBRAIN_REVIEWER` | `reviewer` | Name recorded in the audit log when you claim a review item (`secbrain hitl pull`) |

## Other

`CUDA_VISIBLE_DEVICES` is honoured by the local embedders when `--device auto` or `cuda` is
used. `BAKEOFF_*` variables are read only by the graph-database bake-off harness in
`tools/bake_off/`.
