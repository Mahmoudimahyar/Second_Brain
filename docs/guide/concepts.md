# Concepts

SecBrain answers one question well: **when many sources say different things, what should you
believe, how sure should you be, and can you show your work?** Everything below serves that.

Where a capability is designed but not fully exercised yet, this page says so. The authoritative
list of what is wired and validated is
[`implementation-status.md`](../00-bootstrap/implementation-status.md).

## 1. Trust tiers

Every source is assigned a tier when it is connected, and every node and edge it produces
carries that tier forever.

| Tier | Meaning | Examples |
|---|---|---|
| **L1** | Authoritative, structured | an official dataset, your system-of-record database |
| **L2** | Authoritative, unstructured | an official website, published PDFs |
| **L3** | Structured, non-authoritative | a third-party database or spreadsheet |
| **L4** | Unstructured, non-authoritative | blogs, news, third-party articles |
| **L5** | Community | forums, Reddit, chat exports |

Two rules make tiers safe:

- **L1 is immutable.** A lower-tier claim can never overwrite an L1 fact. When they disagree, the
  lower-tier claim is *flagged* (`l1_clash_invalidated`) and kept — it is evidence of what people
  believe, which is often the interesting part.
- **The operator declares the tier, and L1 is gated.** Connecting an external database as L1
  requires explicit confirmation, and two L1 sources that disagree open a human review item
  instead of silently merging.

**Tiers are a prior, not a sort.** Retrieval does not simply list L1 first. It scores

```text
score = tier weight × rank × temporal decay × author credibility × cross-source consistency
```

so a fresh, corroborated claim from credible community members *can* outrank a stale official
record. That is deliberate: a correct policy change usually appears in the community first.

## 2. Time is a first-class citizen

**Bitemporal edges.** Each edge stores two intervals: when the fact was *true*
(`t_valid_from/to`) and when the graph *knew* it (`t_ingest_from/to`). Updating a fact is an
atomic *supersede* — close the old interval, open a new one — never an overwrite. `as_of`
queries therefore reconstruct exactly what the system believed at any past moment, which is what
makes answers auditable.

**Decay depends on the kind of fact.** Each edge type has its own half-life
(`src/conflict/halo_table.py`):

| Kind of fact | Half-life |
|---|---|
| prices / fees | 1 year |
| policy advice | 1 year |
| opinion & sentiment | 6 months |
| programme requirements, personal anecdotes | 2 years |
| process descriptions (e.g. interview format) | 3 years |
| founding dates, fixed attributes | never decays |

## 3. Five passes, cheapest first

```text
Pass 1  structural graph      $0   authors, posts, threads, replies; entity mentions; credibility
Pass 2  cheap labels          $0   platform metadata (flair, category) → Topic nodes
Pass 3  semantic clustering   ≈$0  local embeddings → clusters; one short LLM summary per cluster
   └─ utility filter ─────────────  drops deleted / bot / empty / no-signal text from LLM input
Pass 4  selective extraction  $    sentiment, atomic claims, questions — only where it pays
Pass 5  retrieval surfaces    $0   hybrid index, ranking, evidence engines
```

The design rule is **the graph keeps everything; only the LLM's input is filtered.** The filter
is reversible: nodes stay in the graph, only the extraction edge is skipped, so you can re-run
Pass 4 later for a topic you initially skipped. On the reference deployment this gate removed
93 % of would-be LLM calls at the comment level.

All model traffic goes through one gateway (`src/gateway/`). Importing a vendor SDK anywhere else
is a lint error, which is what keeps model choice a routing decision rather than a refactor.
Extraction results are cached by a hash of *(text, prompt id + version, schema, model)*, so
re-runs are nearly free.

## 4. Entity resolution

People never use the official name. Resolution snaps a free-text mention to a canonical L1
entity in stages: deterministic fuzzy match → embedding-based blocking → an LLM matcher for the
borderline band. The thresholds are explicit:

| Score | Action |
|---|---|
| ≥ 0.90 | accept automatically |
| 0.75 – 0.90 | queue for human review |
| < 0.75 | reject |

The same machinery links entities *across* sources (`SAME_AS` edges) when you connect an external
database. Cross-source linking is **built but not yet validated on real data**.

## 5. The conflict cascade

When two claims about the same *(subject, predicate)* disagree, the resolver walks an ordered
cascade (`src/conflict/resolver.py`) and stops at the first step that settles it:

| # | Step | Outcome |
|---|---|---|
| 1 | **L1 clash** — a lower-tier claim contradicts L1 | `l1_clash_invalidated` |
| 2 | **Temporal disambiguation** — the claims are about different periods | `temporal_split` (both kept) |
| 3 | **Source-trust weighting** — tier, rank, author credibility. Same-tier, same-period ties go to a **three-vendor LLM judge** with family exclusion; ≥ 2 of 3 must agree | `trust_weighted` / `judge_resolved` |
| 4 | **Disagreement detection** — signed clustering over SUPPORTS / CONTRADICTS edges. *Detects* camps; does not pick a winner. (Built; not yet validated at scale.) | — |
| 5 | **Web verification** — search-grounded check with multiple signals | `web_verified` |
| 6 | **Human review** | `hitl_pending` |

Two principles are worth stating because they are easy to get wrong:

- **Majority is not truth.** Cluster size never decides a conflict. A minority is routed to
  verification, not labelled an anomaly.
- **No collaborator, no guess.** If the judge or verifier is not configured, the cascade
  escalates to a human instead of inventing an answer. You can watch this happen in the
  [quickstart](../../examples/quickstart/README.md#5--when-sources-disagree).

## 6. Human-in-the-loop

Three kinds of decision are reserved for people: borderline entity matches, irreducible
conflicts, and **any change to the schema**. New node or edge types are proposals that must be
approved — there is no ungoverned ontology growth. Review happens in the CLI (`secbrain hitl …`)
or the console, and every decision lands in an append-only audit log.

## 7. Evidence-grade answers

Three retrieval surfaces build on the graph, in increasing rigour:

- **Ask** — natural-language question → graph + consensus + official data → cited answer.
- **Evidence dossier** — broad recall, then filtering; stance positions are *counted over the
  full relevant set*, never estimated from a sample; adjudicated against L1; abstains when there
  is no authoritative anchor.
- **Research protocol** — treats every question as a small experiment. An answer must carry a
  pre-registered denominator, per-bucket estimates with thread-clustered confidence intervals
  and effective sample size, a temporal trend test, a cohort split, a robustness check, a
  selection-bias statement, and provenance — or it is an abstention.

**Provenance is per statistic.** Every number has a `stat_id` that resolves to the exact
records that were counted. Prose is rendered deterministically from those numbers, and an
entailment guard drops any sentence containing a figure the evidence does not support.

**What the protocol admits about itself.** Classifier accuracy is reported as a sensitivity band
unless human gold labels exist; on the reference deployment the bulk sentiment classifier reached
only κ = 0.36 against a stronger reference labeller, and affected answers carry a
low-reliability flag because of it.

## 8. Status words

You will see these throughout the docs. They are defined precisely because the project was once
burned by vague ones ([post-mortem](../00-bootstrap/why-drift-happened.md)):

| Word | Means |
|---|---|
| **Decided** | An ADR chose it. "Locked" and `accepted` mean this and nothing more. |
| **Built** | The module exists and passes unit tests in isolation. |
| **Wired** | A non-test call site in the CLI, a flow, or an API route invokes it. |
| **Validated** | Wired, and exercised on real data with a saved report. |
