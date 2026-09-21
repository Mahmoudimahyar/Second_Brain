# Evals

Offline evaluation harnesses and their gold sets. Everything here runs without an API key.

| Harness | Gold set | Measures |
|---|---|---|
| `alias_resolution.py` | `gold/alias_mentions.jsonl`, `gold/alias_mentions_adversarial.jsonl` | Precision / recall / F1 of the Pass-1 mention extractor against canonical L1 entities |
| `blocking_recall.py` | `gold/v1.5a-cross-graph.jsonl` | Recall of the entity-resolution blocker (candidate generation) |
| `sentiment.py` | `gold/sentiment.jsonl` | Verdict + target-entity accuracy of sentiment extraction |
| `interview_q.py` | `gold/interview_q.jsonl` | Interview-question harvesting |
| — | `gold/v1.5a-mapping-suggestions.jsonl` | Table → node/edge mapping suggestions for external DB connectors |
| — | `gold/v1.5c-web-verify.jsonl` | Web-verification verdicts (stubbed providers) |

```bash
# needs a populated alias table (ingest L1 first)
python -m evals.alias_resolution data/sqlite/store.db evals/gold/alias_mentions.jsonl
```

## Gold-set provenance — no third-party text is committed

Every tracked gold file is **hand-written or synthetically generated**. None contains
verbatim forum posts, usernames, or permalinks.

`gold/alias_mentions.jsonl` deserves a note, because it is *derived from* real data:

1. `build_alias_gold.py` samples a real forum dump and labels posts by exact alias match.
   Its output is verbatim third-party content, so it writes to the git-ignored
   `gold/private/` directory.
2. `build_public_alias_gold.py` reads that private file and keeps only the **surface form**
   each school was referred to by ("UB", "Stony Brook university", "tcdm"). It drops labels
   that pointed at spreadsheet aggregate rows rather than schools (GAP-056) and surface forms
   that are everyday words or ambiguous initialisms ("up", "us", "UT"), then places each
   surviving form in a hand-written carrier sentence. Negatives are hand-written.

The result preserves what the matcher is actually tested on — the real-world distribution of
alias spellings, casing, and abbreviations — without publishing anyone's words.

**Comparability.** The public set is cleaner than the private one, so scores are not
interchangeable. For the same matcher and alias table, measured 2026-09-20:

| Gold set | Entries | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| private real-text (auto-labelled, noisy) | 326 | 0.974 | 0.810 | 0.884 |
| public synthetic-carrier (curated) | 264 | 0.985 | 0.910 | 0.946 |

Alias-resolution figures quoted in validation reports dated before 2026-09-20 were measured on
the private set. The adversarial set
(`alias_mentions_adversarial.jsonl`: misspellings, unknown acronyms, substring traps,
two-school ambiguity) remains the harder and more informative benchmark.

## Contributing gold cases

Write them yourself. Do not paste real posts, even short ones, and do not include usernames
or links to specific threads.
