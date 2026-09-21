# Bring your own platform

SecBrain is source-pluggable: the core engine — graph, entity resolution, conflict cascade,
retrieval, provenance — does not know where a record came from. It only knows its **tier**, its
**timestamps**, and its **shape**. This page says what exists, and what it honestly takes to add
something new.

## What exists today

| Source | Tier | Entry point | Code |
|---|---|---|---|
| Reddit-style dumps (posts + comments JSONL, Pushshift / Arctic-Shift schema) | L5 | `secbrain ingest l5-reddit`, `l5-reddit-batched` (checkpointed, resumable) | `src/ingestion/adapters/l5_reddit.py` |
| Threaded forum dumps (JSONL) | L5 | `secbrain ingest l5-sdn` | `src/ingestion/adapters/l5_sdn.py` |
| HTML files | L2 | `secbrain ingest l2-html` | `src/ingestion/adapters/l2_html.py` |
| PDF documents | L1 | `secbrain ingest l1-pdf` | `src/ingestion/adapters/l1_pdf.py` |
| Spreadsheets of official facts | L1 | `secbrain ingest l1-adea` | `src/ingestion/adapters/l1_excel.py` |
| PostgreSQL dump of a reference database | L1 | `secbrain ingest l1-db`, `l1-residency` | `src/ingestion/adapters/l1_db.py` |
| Live websites — staged crawl: sitemap → entity-tagged → full GraphRAG | L1–L4, declared per domain | `secbrain crawl register / run / tick`, console | `src/ingestion/adapters/crawl4ai_web.py`, `flows/website_*.py` |
| PostgreSQL · MySQL · SQLite · Neo4j (live connectors: discover schema → suggest mapping → pull deltas) | declared per connector, default L2 | console → *Connect a new source*; MCP connector tools | `src/ingestion/sources/` |

Some adapter names (`l1-adea`, `l5-sdn`) come from the first deployment, an education-admissions
community. The L1 adapters in particular encode that domain's entity types (`School`, `Program`).
The live connectors are **built but not yet validated end-to-end on real databases**.

**Not built:** Slack, Discord, Discourse, Zendesk, Stack Exchange, generic REST APIs. They are on
the roadmap; none is claimed here.

## The two extension points

### 1. `DataSource` — for anything that looks like a database

`src/ingestion/sources/base.py` defines the connector protocol: connect, discover a schema
snapshot, sample rows, pull a delta since a cursor, declare a tier. Once a connector yields a
schema, everything downstream already exists — mapping suggestions (table → node type / edge
type / skip), the human review of those suggestions, tier gating, delta scheduling, cross-source
entity linking. A new SQL-ish engine is typically one file modelled on `sqlite.py` or
`postgres.py`, plus registration in `registry.py`.

### 2. `SourceAdapter` — for files and exports

```python
# src/ingestion/adapters/base.py
class SourceAdapter(Protocol):
    source_tier: SourceTier                                   # "L1" … "L5"
    def normalize(self, payload_paths: list[Path]) -> Iterable[object]: ...
```

An adapter is a **pure transformer**: bytes in, typed canonical records out. It never touches
the graph. For a threaded community platform the canonical shape is three dataclasses — a
thread-starting post, a reply, and an author — as in `l5_reddit.py`:

```python
@dataclass(frozen=True)
class RedditPost:     post_id, subreddit, author_user_id, title, selftext, created_utc, score, …
class RedditComment:  comment_id, post_id, parent_id, author_user_id, body, created_utc, …
class RedditUser:     user_id, username, subreddit, first_seen_utc
```

## Worked example: what adding Slack actually takes

Being straight about the size of the job — it is small, but it is not zero:

| Step | What | Rough size |
|---|---|---|
| 1 | **Adapter** `src/ingestion/adapters/l5_slack.py`: parse a Slack export (`channels.json`, `users.json`, one JSON file per day). Map a message with `thread_ts == ts` (or no thread) to a *post*, replies to *comments*, members to *users*; convert `ts` to UTC; namespace authors as `slack:<workspace>:<user>` so identities never collide across platforms. | ~150 lines + tests |
| 2 | **Structural assembly.** `Pass1StructuralBuilder` has one `assemble_*` method per record family (`assemble_reddit`, `assemble_sdn`). Add `assemble_slack` emitting the standard structural edges — `AUTHORED`, `REPLIED_TO`, `BELONGS_TO_THREAD`, `POSTED_IN_FORUM` — and entity mentions via the shared `Pass1MentionExtractor`. | ~100 lines, mostly mirroring `assemble_sdn` |
| 3 | **Credibility rubric.** Author credibility is platform-aware (karma means something different from reaction counts). Add a rubric in `src/credibility/` or reuse the closest one. | ~60 lines |
| 4 | **Entry point.** A `secbrain ingest l5-slack` command (copy `l5-reddit`: register the dump, run the adapter, assemble, upsert, write the audit row) — and a Prefect task in `flows/pass1_structural.py` if you want it scheduled. | ~50 lines |

From there on **nothing else changes**: Pass 2 labels (channels become topics), Pass 3
clustering, Pass 4 extraction, the conflict cascade, retrieval, provenance and the console all
operate on the graph, not on the source.

Two things to decide before writing code:

- **Tier.** A public community is L5. An internal, moderated support channel staffed by your own
  experts might reasonably be L4 or even L3. The tier is a statement about *authority*, not about
  the platform.
- **What you are allowed to ingest.** Exports can contain private messages and personal data.
  Respect the platform's terms, your organisation's policy and privacy law; pseudonymise authors
  at the adapter boundary if you do not need identities.

## Contributing an adapter

Follow [`CONTRIBUTING.md`](../../CONTRIBUTING.md): tests first, synthetic fixtures only (never a
real export), and the capability is done when it is *wired* — reachable from the CLI or a flow,
with the call site cited — not when its unit tests pass.
