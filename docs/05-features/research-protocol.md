# Research Protocol — every answer is a measured estimate

**Status: Built + validated on EC2 (RP-1…RP-5, 2026-06-21).** Wiring site:
`EvidenceDossierEngine.research(question)` → `src/research/protocol.py`. Batch runner:
`cloud/run_research_panel.py`. 32 unit tests `tests/research/`.

## Why

A search engine retrieves; an instrument *estimates with error bars*. Insight questions
("what % of applicants think X", "which schools are best reviewed", "is opinion changing")
are **estimation problems** about a population, measured through a noisy classifier on a
non-random sample. So every answer routes through one protocol that produces:

> estimate · 95% interval · classifier-error band · robustness check · temporal trend ·
> bias label · every number traced to its exact source ids.

No number is produced by the LLM. The LLM only *names* stance/topic buckets; all counts,
proportions, CIs, and trends are deterministic over retained id sets.

## The 9 estimands (one method each)

The ~55 role questions collapse into 9 statistical objects. The router
(`classify_estimand`) maps each question to one; the same statistical core runs for all.

| Estimand | Covers | Bucketing |
|---|---|---|
| `sentiment` | "% positive toward X", "opinion about advising" | graph `SentimentAnnotation.verdict` (deterministic) |
| `stance` | "is X worth it", "DIY vs paid" | LLM-named positions → embedding-counted |
| `topic` | "most-discussed", "content ideas", "use cases" | LLM-named sub-topics → embedding-counted |
| `pain` | "top pain points", "where tools fall short" | topic + affect |
| `belief` | "what applicants get wrong" | stance + L1 adjudication (`engine.answer` verdict) |
| `ranking` | "cheapest & liked", "worst reviewed" | school_metrics + EB shrinkage |
| `price` | "how much would they pay" | regex price extraction (proxy) |
| (modifier) `temporal` | "over time", "in July" | year from `created_iso` (real) |
| (modifier) `segment` | "pre-dental vs students" | subreddit→cohort (proxy) |

## The lab protocol (runs under every answer)

1. **Estimand + denominator** pre-registered (unique-author denominators where possible).
2. **Retrieve** the query-scoped evidence (school recall, or FTS/semantic for topics).
3. **Classify** each doc to a bucket.
4. **Enrich** each doc with `thread_id / author / year / cohort` (`enrich.py`).
5. **Estimate + uncertainty**: per-bucket **Wilson** CI + **thread-clustered bootstrap**
   CI + **effective N** (= n/deff). Thread clustering matters — reply chains echo, so 348
   comments in 50 threads are far fewer than 348 independent observations.
6. **Consensus** (entropy/HHI) for stance; **EB shrinkage** for rankings (a 19-comment
   school can't top a 119-school list by chance).
7. **Measurement-error sensitivity**: Rogan–Gladen band over a plausible classifier
   sens/spec range. *No human gold set → a range, not a point — and we say so.*
8. **Robustness**: re-classify at a stricter cosine floor (same buckets) → top bucket
   stable within 5pts? Sentiment is a deterministic graph count → no threshold to perturb.
9. **Temporal**: slice by year → inverse-variance-weighted **trend test** (real drift vs
   noise — the cross-year "consensus change" experiment).
10. **Cohort split** (proxy) when segment is asked. **Bias label** always. **Provenance**:
    every bucket → `stat_id` → `GET /api/v1/dossier/sources?stat_id=` drill-down.

## The statistics (`src/research/stats.py`, numpy + stdlib only)

`wilson_ci` · `cluster_bootstrap_ci` (deff + n_eff) · `eb_shrink` (beta-binomial) ·
`rogan_gladen` + `rogan_gladen_band` · `consensus_index` · `trend_test` (weighted WLS) ·
`resonance`. All seeded/deterministic — identical re-run.

## Success criteria + the honest ceiling

`quality.assess_dossier` scores each answer against 10 criteria. **8 are automatically
checkable today** (denominator, clustered CI, shrinkage, robustness, temporal, bias,
provenance, determinism). **2 are GATED** and reported separately, never silently passed:

- `calibrated_corrected` — true *accuracy* needs a human-labeled gold set to estimate the
  classifier's P/R and bias-correct. Today we ship the **sensitivity band**, not a
  gold-calibrated point.
- `human_spotcheck` — a person confirming the top-k provenance.

This is the gap between **precise** (we have it: deterministic counts + provenance) and
**accuracy-validated** (needs a labeling budget). The single highest-leverage next build
is the gold-label sets (~300–500 items/estimand) that close both gated criteria.

## Known proxies (labeled in every dossier)

- **cohort** = subreddit (r/predental=applicant, r/DentalSchool=student, r/Dentistry=pro);
  specialty cohorts (Endo/OMFS) are topic-retrieval, not a clean cohort.
- **price** = regex over mentioned dollar amounts (reported-paid, contaminated by tuition/
  loan figures) — a distribution with caveats, not a willingness-to-pay survey.
- **forum bias** — self-selected, vocal, negativity-skewed; sentiment is a *lower bound* on
  satisfaction. Stated in every answer.
