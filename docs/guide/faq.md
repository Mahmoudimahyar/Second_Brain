# FAQ

### Is this production-ready?

No, and it does not pretend to be. It is pre-1.0 research software, **single-tenant and
local-first**: the API has no authentication and is not meant to face the internet. What it *is*:
a complete, tested, end-to-end implementation of an idea, proven on a multi-million-document
corpus. The honest status of every capability — `Decided`, `Built`, `Wired` or `Validated` — is
in [`implementation-status.md`](../00-bootstrap/implementation-status.md).

### Does it come with data?

No. This repository is code and documentation. The quickstart uses a tiny, entirely fictional
dataset that a script generates. Test fixtures and eval gold sets are synthetic or hand-written.
You bring your own sources — and you are responsible for having the right to ingest them.

### How is this different from vector RAG?

Vector RAG retrieves text that *sounds* relevant and lets a model paraphrase it. It has no notion
of who said it, when it was true, or whether another source contradicts it. SecBrain keeps
source tier, author credibility and two timelines on every edge, resolves contradictions through
an explicit cascade, and returns *counted* evidence with confidence intervals and per-statistic
provenance — or abstains.

### How is it different from off-the-shelf GraphRAG engines?

Those are good at building a graph and summarising it. SecBrain's contribution is the layer they
leave out: trust tiers, temporal-first conflict resolution, and statistical answer protocols.
Whether to build that layer on top of an existing engine was tested rather than assumed —
see [ADR-025](../11-decisions/ADR-025-graphrag-engine-evaluation-spike.md).

### Which platforms does it support?

Reddit-style dumps, threaded forum dumps, websites (a polite staged crawler), HTML / PDF /
spreadsheet files, and PostgreSQL / MySQL / SQLite / Neo4j connectors. Slack, Discord and similar
are **not** built; [adding one](adapters.md) is a few hundred lines because everything after the
adapter is source-agnostic.

### Do I need API keys? A GPU?

Not to install, run the 1,200+ tests, follow the quickstart, or build the structural graph —
Passes 1 and 2 are deterministic and free. Keys are needed for the LLM passes and the judge.
A GPU is optional: embeddings default to CPU, and the reference run embedded ~877 K posts on
CPU in about two hours.

### What does it cost to run?

On the reference deployment, LLM extraction over every post cost about $119 and over 1.95 M
comments about $34, after a utility gate removed 93 % of would-be calls. Clustering the full
corpus cost under a cent. The design principle is that cheap deterministic passes do the
structural work and models are used only where they pay for themselves.

### Why Kùzu?

It won a bake-off on real data on operational simplicity: an embedded database with no server to
run, and point lookups far inside the latency budget
([ADR-001](../11-decisions/ADR-001-graph-db.md)). The graph is accessed through a `GraphClient`
protocol, so the store is replaceable. One caveat stated in the ADR: upstream Kùzu has been
archived, so the project stays on the last published 0.11 line and tracks a maintained fork as
the fallback.

### Why is LangChain banned?

A lint rule forbids it, along with direct vendor-SDK imports outside `src/gateway/`
([dependency rules](../04-architecture/dependency-rules.md)). The project wants every model call
to pass through one small, typed, testable gateway so that vendors are swappable and costs are
attributable. That is easier to guarantee with no orchestration framework in the way.

### Why are there school names in the tests?

The first deployment was an education-admissions community, so bundled adapters and fixtures
use that vocabulary. Fixture values are synthetic. Nothing in the core engine depends on the
domain — it lives in the adapters and in whatever canonical entity list you load as L1.

### Was this written by AI?

Much of the code was written with AI coding agents, under a harness the repository documents
openly: operating rules ([`AGENTS.md`](../../AGENTS.md)), a repo-context MCP server so agents
retrieve instead of reading everything, and gates that fail the build when documentation claims
more than the code delivers. The post-mortem of the time that harness failed is
[here](../00-bootstrap/why-drift-happened.md) — it is the most useful document in the repo.

### What is it weak at, today?

Stated plainly in the [README](../../README.md#proven-at-scale): a bulk sentiment classifier with
only moderate agreement against a stronger labeller; two research-protocol criteria gated on
human gold labels that do not exist yet; 72 % line coverage against an 80 % target; lint and
strict-typing ratchets that are not yet at zero; several connectors built but not validated on
real data; a graph canvas in the console that is still a stub.

### How do I contribute?

Read [`CONTRIBUTING.md`](../../CONTRIBUTING.md). The bar is *small, evidenced, wired*: tests
first, synthetic fixtures only, and a capability counts as done when a real entry point calls it.
