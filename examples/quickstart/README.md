# Quickstart — the whole idea in two minutes

No API keys. No GPU. No dataset to download. Everything here is **fictional** — five made-up
schools, seven made-up forum users — and every output block below is pasted from a real run.
[`tests/examples/test_quickstart.py`](../../tests/examples/test_quickstart.py) replays this
walkthrough in CI, so it cannot quietly stop being true.

The scenario: an *official* spreadsheet says one thing; a *community forum* says many things,
some outdated, some wrong, some right. SecBrain's job is to hold both, know which is which, and
never lose track of where anything came from.

```bash
pip install -e ".[dev]"                                   # once, from the repo root
python examples/quickstart/make_demo_data.py demo/in      # writes 3 small files
```

## 1 · Load the source you trust (tier L1)

```bash
secbrain --data-dir demo/data ingest l1-adea demo/in/reference_2024-25.xlsx
```

```text
ok reference_2024-25.xlsx: cycle=2024-25 schools=5 metrics=10 dup=False
Done. schools=5 metrics=10 aliases=5
```

Five canonical entities, ten official facts. L1 is immutable ground truth: nothing ingested
later is allowed to overwrite it. (`l1-adea` is the bundled spreadsheet adapter; its name comes
from the first deployment.)

## 2 · Load the community (tier L5)

```bash
secbrain --data-dir demo/data ingest l5-reddit demo/in/demo_forum.jsonl demo/in/demo_forum_comments.jsonl
```

```text
ok reddit r/demo_forum: posts=10 comments=12 users=7 nodes=30 edges=68
ok pass2: topics=4 references_topic_edges=10
```

Pass 1 built the structural graph — authors, posts, reply threads — and, because a canonical
backbone already exists, **linked posts to the entities they mention**. Pass 2 turned forum
flair into topic nodes. Cost of both passes: $0, no model involved.

```bash
secbrain --data-dir demo/data stats
```

```text
     Graph nodes
┌───────────┬───────┐
│ label     │ count │
├───────────┼───────┤
│ School    │     5 │
│ Metric    │    10 │
│ CycleYear │     1 │
│ Subreddit │     1 │
│ User      │     7 │
│ Post      │    10 │
│ Comment   │    12 │
│ Topic     │     4 │
└───────────┴───────┘
Total nodes: 50
Total edges: 88
Audit log rows: 2
```

## 3 · People never use the official name

```bash
secbrain --data-dir demo/data canonical "Lakemont"
```

```json
{
  "canonical_id": "school:lakemont_college_of_dental_medicine",
  "canonical_name": "Lakemont College of Dental Medicine",
  "type": "School",
  "match_confidence": 1.0,
  "aliases": ["Lakemont College of Dental Medicine", "Lakemont", "LCDM"]
}
```

Nobody typed `LCDM` anywhere — the alias expander derived it. And the engine knows what it does
not know:

```bash
secbrain --data-dir demo/data canonical "Hogwarts Dental"
# No L1 match for 'Hogwarts Dental'
```

In a real ingest, matches scoring ≥ 0.90 are accepted, 0.75–0.90 go to a human review queue
(`secbrain hitl list`), and anything lower is rejected.

## 4 · Ask about an entity: official first, community after, everything cited

```bash
secbrain --data-dir demo/data query "Marlowe" --no-hybrid --limit 5
```

```text
┌─────────────────────────────────────────────────┬────────┬──────┬──────────────────────────┐
│ node_id                                         │ type   │ tier │ refs                     │
├─────────────────────────────────────────────────┼────────┼──────┼──────────────────────────┤
│ school:marlowe_university_college_of_dentistry  │ School │ L1   │ …, dump:1a295a3b259a04d0 │
│ metric:school_marlowe_university_college_of_de… │ Metric │ L1   │ …, dump:1a295a3b259a04d0 │
│ metric:school_marlowe_university_college_of_de… │ Metric │ L1   │ …, dump:1a295a3b259a04d0 │
│ reddit_post:p03                                 │ Post   │ L5   │ reddit_post:p03          │
│ reddit_post:p09                                 │ Post   │ L5   │ reddit_post:p09          │
└─────────────────────────────────────────────────┴────────┴──────┴──────────────────────────┘
```

The official record and its facts, then the two forum posts that talk about it — each row
carrying its tier and a reference back to the exact dump or post. `p03` (2019) says tuition is
"about 30k"; `p09` (2025) says "it is NOT 30k anymore". Which brings us to the interesting part.

> **About `--no-hybrid`.** This is the entity-seeded graph traversal. The default hybrid mode adds
> BM25 + vector search; its keyless default embedder (`hash`) is a dependency-free stand-in, *not*
> a semantic model, so on a 50-node toy graph it mostly adds noise. For real semantic search
> install the `embeddings` extra and pass `--embedder bge` or `--embedder qwen`.

## 5 · When sources disagree

```bash
python examples/quickstart/conflict_cascade.py
```

```text
A forum post repeats an old number; the official sheet disagrees
  new      : forum:p03-repeated       30,000  (L5, 2025)
  existing : official:2025            47,800  (L1, 2025)
  → l1_clash_invalidated   winner: official:2025
    L1 source is immutable; non-L1 claim invalidated (FR-6.1)

Two community claims about DIFFERENT years
  new      : forum:c04                30,000  (L5, 2019)
  existing : forum:old-thread         33,000  (L5, 2017)
  → temporal_split   winner: forum:c04
    non-overlapping t_valid_* windows (FR-6.2)

Same year, same tier — but one author has a far better track record
  new      : forum:newbie             52,000  (L5, 2025)
  existing : forum:veteran            48,000  (L5, 2025)
  → trust_weighted   winner: forum:veteran
    existing claim's credibility outranks incoming (FR-6.3)

Same year, same tier, equally credible authors, and no judge available
  new      : forum:peer-a             46,000  (L5, 2025)
  existing : forum:peer-b             49,500  (L5, 2025)
  → hitl_pending   winner: —
    no deterministic rule applies; escalate to HITL (ADR-006 step 6)
```

That script calls the production `ConflictResolver` directly. Four disagreements, four different
right answers:

1. **Official beats forum** — and the forum claim is *flagged*, not deleted.
2. **Different years are not a conflict.** "30k in 2019" and "33k in 2017" can both be true.
3. **Track record breaks ties** between community members.
4. **Real ambiguity goes to a person.** With keys for all three model families configured, a
   three-vendor LLM judge (≥ 2 of 3 must agree) and a web-verification step get a turn first;
   without them, the engine escalates rather than guesses.

## Where to go next

| To… | Do |
|---|---|
| Open the operations console | `cd web && pnpm install && cd ..`, then `SECBRAIN_DATA_DIR=demo/data secbrain ui` (the API reads the data directory from the environment) |
| Give an AI agent access to it | [`docs/guide/mcp.md`](../../docs/guide/mcp.md) |
| Run the LLM passes (sentiment, claims, questions) | set keys in `.env`, then `secbrain extract` — see [configuration](../../docs/guide/configuration.md) |
| Bring your own platform | [`docs/guide/adapters.md`](../../docs/guide/adapters.md) |
| Understand the design | [`docs/guide/concepts.md`](../../docs/guide/concepts.md) |

Clean up with `rm -rf demo`.
