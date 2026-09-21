# R-007 — Multi-source KG construction, conflict resolution, user credibility (SOTA survey, 2024–2026)

> Live-web survey dispatched per `research-protocol.md`. Three streams (a/b/c). Sources cited inline by URL; key papers linked in their respective subsections. All recommendations are draft and feed into R-007 → ADR pipeline once Mahyar ratifies.

---

## R-007a — Multi-source KG construction with heterogeneous trust tiers

### 1. Trust modeling in production KGs (Wikidata / DBpedia / YAGO)

Wikidata's model is the most-cited prior art for explicit trust on a per-claim basis and maps almost 1:1 to our needs:

- **Rank on every statement**: every Wikibase statement has one of three ranks — `preferred`, `normal`, `deprecated`. Default is `normal`; `preferred` wins when multiple values exist; `deprecated` statements are filtered out by default but kept for provenance. `reason for deprecated rank` (P2241) and `reason for preferred rank` (P7452) qualifiers explain *why*. See https://www.wikidata.org/wiki/Help:Ranking.
- **References**: every statement can carry zero or more references (provenance pointers). A statement without a reference is allowed but discouraged.
- **Qualifiers**: temporal/contextual metadata attached to a statement (e.g., `point in time`, `valid from`, `valid until`, `determination method`). This is how Wikidata expresses "the mayor of Paris between 2014 and 2020" alongside the current mayor without conflict.
- **YAGO4** keeps only `preferred`-rank statements from Wikidata, dropping stale facts; YAGO2 used SPOTLX 6-tuples (subject/predicate/object/time/location/context) for richer provenance.

DBpedia's provenance work (Modelling provenance of DBpedia resources using Wikipedia contributions, https://www.sciencedirect.com/science/article/abs/pii/S1570826811000175) attaches a separate provenance graph keyed by Wikipedia edit history — a pattern that fits a separate audit log rather than inline triple properties.

**Takeaway**: the `preferred/normal/deprecated` × `references` × `qualifiers` shape is exactly the trust + temporality + provenance triad we already declared in R0/R2. Adopt it semantically; we don't need Wikibase as a back-end.

### 2. Truth-discovery algorithms — are they still useful in 2026?

The classical truth-discovery family (TruthFinder 2007, Investment, PooledInvestment, AccuPR, 2-Estimates / 3-Estimates, LCA, LTM, Cosine) iteratively co-estimates **source trust** and **claim trust** from the same observation matrix — see "Truth Discovery Algorithms: An Experimental Evaluation" (https://arxiv.org/pdf/1409.6428) and the KDD survey (https://www.kdd.org/exploration_files/Article1_17_2.pdf). DAFNA-EA on GitHub (https://github.com/daqcri/DAFNA-EA) is a reference Java implementation of 12 algorithms.

Where they still win in 2026: **multi-source numeric/categorical conflicts on a shared object-attribute schema** (e.g., 50 sources claim the average DAT for UCLA in 2022; classical methods extract a robust estimate by down-weighting consistently wrong sources). They do NOT solve free-text reconciliation, nor do they handle temporal drift — both critical for us.

The Latent Truth Model (LTM, Zhao et al., VLDB 2012) is the most defensible probabilistic option because it models **false-positive** and **false-negative** error rates separately per source — a near-perfect fit for "L5 user X is reliable on topic Y but wrong on topic Z." A 2018 RBM-LTM extension (https://arxiv.org/pdf/1807.10680) replaces the closed-form prior with a neural latent space — overkill for V1.

**Verdict for V1**: do NOT build a classical TD model in V1. Use Wikidata-style rank + qualifiers + our trust-tier prior, and only escalate to LTM when we have a per-numeric-attribute conflict where >5 L4/L5 sources disagree — at which point LTM gives us a defensible weighted estimate and a per-source reliability score that feeds back into the user-credibility graph (R-007c).

### 3. GraphRAG family — does any surface source-trust as a first-class concept?

Surveyed: Microsoft GraphRAG, LazyGraphRAG, HippoRAG / HippoRAG 2, LightRAG, nano-graphrag, fast-graphrag, MedGraphRAG, PathRAG, E2GraphRAG. The Awesome-GraphRAG curated list (https://github.com/DEEP-PolyU/Awesome-GraphRAG) is the best index.

Findings:

- **Microsoft GraphRAG / LazyGraphRAG**: pre-generates community summaries with provenance pointers back to source chunks. Source attribution is supported but is at the **chunk** level, not the **claim** level — there is no `source_tier` weighting in the graph extraction or in the local-vs-global search. LazyGraphRAG (June 2025) defers community generation until query time to reduce build cost. Per https://www.microsoft.com/en-us/research/blog/graphrag-unlocking-llm-discovery-on-narrative-private-data/, the provenance audit story is solid but conflict handling is "present multiple voices to the user" — i.e., no automatic resolution.
- **HippoRAG / HippoRAG 2** (NeurIPS 2024 / ICML 2025, https://arxiv.org/abs/2502.14802): dual-node KG (passage + phrase) + Personalized PageRank + LLM-based triple filtering. 10–30× cheaper multi-hop retrieval. No native source-trust concept; PPR seeding could be biased by trust tier but that's our extension, not theirs.
- **LightRAG** (Jan 2025, https://www.analyticsvidhya.com/blog/2025/01/lightrag/): entities + relationships rather than community summaries; designed for cheaper local LLM operation. No trust-tier modeling.
- **nano-graphrag / fast-graphrag**: minimal LightRAG-style implementations. No trust modeling.
- **Graphwise GraphRAG** (https://graphwise.ai/blog/introducing-graphrag-the-trust-layer-of-the-graphwise-platform/) markets itself as "the trust layer" — but the trust they describe is **explainability/audit**, not multi-tier source weighting. Closer to our V2 "marketing positioning" than our V1 mechanism.
- **WildGraphBench** (Feb 2026, https://arxiv.org/pdf/2602.02053): a new benchmark for GraphRAG on "wild" (heterogeneous, noisy) corpora. Worth watching — it explicitly tests heterogeneous-source robustness.

**Verdict**: no off-the-shelf GraphRAG library models multi-tier source trust as a first-class citizen. Our `source_tier` ladder is genuinely under-published; building it ourselves is justified. Borrow HippoRAG 2's PPR + dual-node structure as the retrieval backbone and bias the PPR teleport vector by `source_tier` to get tier-aware retrieval almost for free.

### 4. Entity resolution at 500K × 1K scale

The problem shape: ~500K Reddit/SDN thread mentions of school/program names × ~1K canonical L1 entities (US dental schools + residency programs + variants). Naive cross-join = 500M pair-wise comparisons — infeasible without blocking. The good news: the canonical side is tiny (1K), so this is closer to **classification-against-fixed-vocabulary** than symmetric record linkage.

Options surveyed:

- **Splink 2024–2026** (https://moj-analytical-services.github.io/splink/): Fellegi–Sunter probabilistic linkage, DuckDB / Spark / Athena backends. Benchmarks: 7M-record dedup in 2 minutes on a laptop (https://medium.com/data-science-collective/deduplicating-7-million-records-in-two-minutes-with-splink-4b1a87035a85); 1M-record linkage in ~1 minute. UK Ministry of Justice runs it in production (https://moj-analytical-services.github.io/splink/blog/2026/01/29/running-splink-in-production.html). Strength: probabilistic, explainable, fits L1-canonical reference data well. Weakness: assumes structured records — works best when both sides have name + address + DOB + etc., not "free-text mention in a Reddit post."
- **Dedupe.io (dedupe Python library)**: similar Fellegi–Sunter approach with active-learning UX; smaller community in 2026 than Splink.
- **Senzing**: commercial-grade ER core (https://senzing.com/senzing-architecture/). 100+ OSS adjacent assets. Pricing by record volume — likely not free for our 500K. Overkill for V1 internal-only; reconsider for V2.
- **DITTO** (https://arxiv.org/pdf/2004.00584, VLDB 2020): pre-trained Transformer (BERT/DistilBERT/RoBERTa) cast as sequence-pair classification. +29% F1 over pre-2020 SOTA. Per WDC Products benchmark (https://webdatacommons.org/largescaleproductcorpus/wdc-products/, EDBT 2024), DITTO is within 2% F1 of more complex models like HierGAT — i.e., DITTO is still the SOTA-ish workhorse in 2025–2026.
- **HierGAT**: hierarchical graph attention layered over Transformer. Marginal F1 gain over DITTO at significantly higher engineering cost. Not worth it for V1.
- **R-SupCon** (supervised contrastive entity matching): on par with DITTO/HierGAT on WDC Products.
- **Entity-embed** (https://github.com/vintasoftware/entity-embed): PyTorch contrastive learning → ANN. Open source, well-documented.
- **SC-Block** (https://arxiv.org/pdf/2303.03132): supervised contrastive learning for **blocking**, not matching. 1.5–2× pipeline speedup, half the candidate-set size.
- **BlockingPy** (Apr 2025, https://arxiv.org/pdf/2504.04266): ANN-based blocking from raw text or embeddings — newer alternative to Splink's deterministic blocking.
- **A Robust and Efficient Pipeline for Enterprise-Level Large-Scale Entity Resolution** (Aug 2025, https://arxiv.org/abs/2508.03767): the most relevant recent paper — production lessons for ER at our scale and above.

**Recommendation (R-007a deliverable)**:

```
Stage A (blocking): BGE-small embedding of each thread-mention string;
                    cosine-NN against pre-embedded L1 canonical names + aliases
                    using HNSW (Kùzu native or FAISS).  top_k=20.
Stage B (scoring):  DITTO-style sequence-pair classifier (DistilBERT, fine-tuned
                    on ~2K HITL-labeled pairs from V1 alpha).  Output =
                    similarity ∈ [0,1].
Stage C (thresholds, per R0): auto-accept ≥0.90, HITL 0.70-0.90, reject <0.70.
Stage D (provenance): every accepted match writes (mention_id, canonical_id,
                       score, method, model_version, timestamp) to the audit log.
```

Why not Splink: Splink shines on structured-record dedup. We have 500K *free-text mentions* → 1K canonical entities — a classification/snap-to-canonical problem, not symmetric dedup. The embedding-NN + DITTO-style reranker pipeline is a better fit and is the same pattern that won WDC Products. Revisit Splink for V2 if/when we ingest structured CSVs (e.g., a partner company's CRM dump).

### 5. Real-world case studies — authoritative vs scraped reconciliation

- **Bloomberg** (https://www.bloomberg.com/company/press/waterstechnology-knowledge-graphs-data-quality-and-reuse-form-bloombergs-ai-strategy/): explicit data-management discipline around lineage and provenance; reusable training/eval data is a side benefit. Their taxonomy-first approach (define corporate-bond type → coupon property → instance fills) mirrors our L1-anchor-first plan. They do NOT publish their reconciliation algorithm; the public lesson is "treat lineage as a product, not a side-table."
- **LinkedIn Economic Graph**: limited public detail on internal trust-tier modeling. Used in product but not described in research-paper depth.
- **Diffbot** (https://blog.diffbot.com/knowledge-graph-glossary/data-provenance/): every fact carries a provenance tag of one of two types — `extracted from public web` or `computed from public web`. Two-tier rather than five-tier; closer to our L4/L5 distinction than the full ladder.
- **Google Knowledge Graph**: opaque externally; the Knowledge Vault paper (Dong et al., KDD 2014) is the closest public artifact — uses confidence scoring per fact computed from multiple extractors voting.

**Synthesis**: nobody publicly publishes a five-tier ladder like ours. The closest analogs are (1) Wikidata's three-rank + reference model, (2) Diffbot's two-class provenance, and (3) Knowledge Vault's confidence-from-extractor-voting. Our five-tier ladder is novel enough to be worth writing up as an ADR appendix once V1 is real.

---

## R-007b — Conflict resolution at scale in temporal KGs

### 1. Bitemporal modeling — Neo4j vs TerminusDB vs Graphiti/Zep

- **Neo4j**: no native bitemporal type, but a well-documented pattern of duplicating nodes/edges per version with `valid_from`, `valid_to`, `tx_from`, `tx_to` properties (https://dev.to/satyam_shree_087caef77512/a-practical-guide-to-temporal-versioning-in-neo4j-nodes-relationships-and-historical-graph-1m5g). Production-grade reference implementations exist for time-travel queries and historical reconstruction.
- **TerminusDB**: native immutable + branchable graph store — every commit is addressable. Closest off-the-shelf bitemporal model but pre-1.0 in some respects and smaller community than Neo4j/Kùzu.
- **Graphiti / Zep** (https://arxiv.org/abs/2501.13956, KGC 2025): **the cleanest off-the-shelf bitemporal GraphRAG library in 2025**. Every edge has explicit validity intervals and a separate ingestion timestamp ("when the fact was true" vs "when we learned the fact"). Beats MemGPT on Deep Memory Retrieval (94.8% vs 93.4%) and beats baselines on LongMemEval by up to 18.5% accuracy with 90% lower latency. Hierarchical episodic / semantic / community subgraph structure matches our user-actor / post-doc / opinion 3-layer plan almost exactly. https://github.com/getzep/graphiti is MIT-licensed.

**Verdict**: even if we stay on Kùzu for the columnar/HNSW advantages, **steal Graphiti's bitemporal edge model wholesale**: every edge stores `t_valid_from`, `t_valid_to`, `t_ingest_from`, `t_ingest_to` (open-ended `t_ingest_to` = current). This is a property addition, not a back-end change. The Kùzu vs Neo4j vs TerminusDB decision is orthogonal.

### 2. Temporal decay functions — half-life, per-topic vs global

The state-of-the-art paper is **HALO (May 2025, https://arxiv.org/pdf/2505.07509)** — "Half Life-Based Outdated Fact Filtering in Temporal Knowledge Graphs." Three modules:

1. Temporal-fact attention captures fact evolution over time;
2. Dynamic relation-aware encoder predicts a per-fact half-life;
3. Outdated-fact filter applies `weight(t) = (1/2)^((now - t_obs)/half_life)` to score validity.

Two key insights for us:

- **Per-relation half-life, not global**. A "school tuition" fact has half-life ~1 year; "department chair name" ~3 years; "school founding year" ~∞. HALO learns half-life per relation type via the dynamic encoder. We can either learn it (V2) or hand-set a half-life lookup table per edge type (V1) — see proposed table below.
- **Per-topic, not per-source**. HALO does not weight by source trust; it weights by recency. This composes cleanly with our `source_tier` weighting — we get `effective_trust(claim) = source_tier_weight × temporal_decay(t_now - t_obs, half_life(edge_type))`.

Related work: **MRAG** (https://arxiv.org/pdf/2412.15540, Dec 2024), **TEMPRAGEVAL** repurposes TIMEQA and SITUATEDQA for diagnostic time-sensitive RAG evaluation, **ChronoQA** (300K news articles, 5,176 questions, 2019–2024) is a current benchmark. **RAG Meets Temporal Graphs** (Oct 2025, https://arxiv.org/html/2510.13590v1) and **Temporal RAG via Graph** (https://arxiv.org/pdf/2510.16715) are the most recent surveys.

**Recommended V1 decay table** (subject to HITL calibration):

| Edge type | Half-life | Justification |
|---|---|---|
| `school.tuition` | 1 yr | Updated annually by ADEA |
| `school.avg_dat` | 2 yr | Cycle-level signal, slow to drift |
| `school.acceptance_rate` | 2 yr | Same as avg_dat |
| `school.department_chair` | 3 yr | Personnel turnover |
| `school.curriculum_emphasis` | 5 yr | Slow programmatic shift |
| `school.founding_year` | ∞ (no decay) | Immutable fact |
| `program.location` | ∞ | Effectively immutable |
| `user_opinion.recommendation` | 2 yr | Opinion drifts |
| `user_opinion.interview_question` | 3 yr | Programs reuse questions; slow shift |
| `user_opinion.sentiment_about_program` | 18 mo | Most volatile |

The `valid_until` qualifier is **hard** (a value stops applying); the half-life decay is **soft** (a value is gradually less trusted but not deleted). Keep both.

### 3. Consensus clustering on text claims — 2025 SOTA

Surveyed: Leiden, HDBSCAN, BERTopic, CDLib's 39 algorithms, signed-network polarized-community detection, neural balance-aware approaches.

- **Leiden** (still the gold standard for modularity-based community detection, https://neo4j.com/docs/graph-data-science/current/algorithms/leiden/): well-supported in Neo4j GDS and scikit-network. SpatialLeiden (Genome Biology, Feb 2025) extends with spatial weighting.
- **HDBSCAN** (density-based, no `k`): pairs well with embedding-based topic vectors. Leiden and HDBSCAN show NMI > 0.65 agreement, so they're complementary not redundant.
- **BERTopic** is at v0.17.4 as of Dec 2025 (https://maartengr.github.io/BERTopic/changelog.html) — **there is no BERTopic 2.0 yet** despite the question prompt. Recent additions: Multi-GPU UMAP for MEGA-scale, Model2Vec lightweight embeddings, zero-shot topic modeling, hierarchical visualization. Still the production-best topic-modeling library for 2026 forum data.
- **CDLib** (https://cdlib.readthedocs.io/): meta-library with 39 community-detection implementations. Use when comparing.
- **Signed-network polarized-community detection** (https://arxiv.org/pdf/2502.02197, Feb 2025; https://link.springer.com/article/10.1007/s10994-024-06581-4, ML journal 2024): the right tool when we want to detect "two camps that disagree" (e.g., on a school's reputation). SUPPORTS/CONTRADICTS edges in our opinion layer are literally signed — we should use a signed-graph community-detection algorithm (e.g., the γ-polarity neural-net approach, Bonchi et al.'s 2pc, or local-spectral methods) on the opinion subgraph, not vanilla Leiden.
- **Reddit polarization** (https://arxiv.org/html/2510.27467v1, Oct 2025): Louvain + statistical edge sparsification to denoise before community detection. Pattern to copy.

**Recommended pipeline**:

```
Per-topic opinion-cluster build (offline, monthly):
  1. Collect claims (from extraction stage) attached to a topic node.
  2. Build a claim-claim similarity graph via BGE-small embeddings + cosine top_k=15.
  3. Add SUPPORTS / CONTRADICTS edges from extracted relations → signed graph.
  4. Sparsify by statistical edge validation (per Reddit-polarization paper).
  5. Run γ-polarity / signed-Leiden to produce camps + neutral middle.
  6. Per camp, BERTopic-summarize the central claims.
  7. Compute camp size (weighted by user_credibility from R-007c).
  8. The "consensus" = largest weighted camp; "outliers" = minority camps tagged
     Status: Anomaly but preserved (R-007c outlier-preservation rule).
```

### 4. Web-verification agents — safe to use in 2026?

As of March 2026, **Claude Computer Use** is in research preview on macOS (Windows by Q3 2026, https://www.cnbc.com/2026/03/24/anthropic-claude-ai-agent-use-computer-finish-tasks.html). **OpenAI Codex Background Computer Use** (Apr 16 2026, separate macOS environment). Both are still classified as production-preview-grade, not production-grade. Both have known failure modes (page-DOM brittleness, prompt-injection from open web).

For our use case ("read a graph claim and confirm against live web"), the dedicated fact-checking literature in 2025–2026 is more relevant than the general-purpose computer-use agents:

- **GraphCheck** (https://pmc.ncbi.nlm.nih.gov/articles/PMC12360635/): extracts a fact KG from a long-form text, then checks each extracted edge against a reference graph. Pattern: extract → verify per edge, not free-form re-read.
- **Multi-Modal Fact-Verification Framework** (https://arxiv.org/pdf/2510.22751): RAG over DBpedia/Wikidata to verify generated claims.
- **HMAC-signed tool receipts** (https://arxiv.org/pdf/2603.10060): cryptographic receipts that an agent cannot forge — a deployable hallucination-detection primitive. Likely overkill for V1 but worth noting.

**Verdict**: do NOT plug Claude Computer Use or Operator directly into the conflict-resolution path for V1. **Instead**, our outbound MCP tool `get_pending_verifications()` produces a list of claims; a **separate crawler** (already out of V1 scope) fetches authoritative URLs; the **fetched dump** is re-ingested through the L1/L2 adapter, which automatically re-runs conflict resolution. The computer-use agent is a V2 experiment, not V1 primary path.

### 5. LLM-as-judge — when OK, when HITL mandatory

Evidence from 2025–2026 is unambiguous about failure modes:

- Frontier models exceed **50% error rates** on JudgeBiasBench (Hongli Zhou et al., 2025): https://www.adaline.ai/blog/llm-as-a-judge-reliability-bias.
- Even SOTA judges average **Fleiss' κ ≈ 0.3** on inter-judge agreement, with much worse performance on low-resource languages.
- Documented biases: position bias, verbosity bias, recency bias, provenance hierarchy bias (EXPERT > HUMAN > LLM > UNKNOWN), shortcut/format bias.
- Calibration mitigations (https://arxiv.org/pdf/2509.26072, https://arxiv.org/abs/2605.06939): (a) calibrate against human spot-checks on the specific domain; (b) reference-guided grading; (c) **meta-judge** rather than debate (debate amplifies bias); (d) **cross-vendor**: judge model from a different vendor than generator.
- A Survey on LLM-as-a-Judge (https://arxiv.org/html/2411.15594v6) is the best 2024–2026 overview.

**Recommended decision rule** for our conflict resolver:

| Conflict signal | Action |
|---|---|
| L1 clash (any tier vs L1) | Invalidate non-L1, no LLM. |
| Two L5 claims, different `created_utc` years | Auto-split by year (temporal disambig). No LLM. |
| Two L5 claims, same year, tier-equal | LLM-as-judge with **reference-guided** prompt (cite L2/L3 if any exist) AND cross-vendor judge (Haiku 4.5 + a Sonnet 4.6 second-opinion when budget allows). If judges disagree → HITL. |
| L4 vs L5 mismatch | Tier weight wins; no LLM needed. |
| Numeric value across 5+ low-tier sources | LTM (truth discovery) — defer to algorithm, no LLM. |
| New node/edge type emerging | HITL mandatory (per existing hard rule). |
| Signed-graph community-detection produces 2 balanced camps | HITL — irreducible disagreement, present both to reviewer. |

This gives us LLM-as-judge only in the narrowest, lowest-stakes slice (tie-breaking between equal-tier same-year claims), with explicit calibration discipline. Everything higher-stakes goes to deterministic rules or HITL.

---

## R-007c — User-credibility scoring + opinion-consensus for forum data

### 1. StackOverflow / Stack Exchange reputation literature

Citations:

- **Predictive Analytics for Collaborators Answers, Code Quality, and Dropout on Stack Overflow** (https://arxiv.org/pdf/2506.18329, Jun 2025): benchmarks 20+ algorithms for predicting Stack Overflow user answer quality and dropout. Features that mattered most: post history depth, time-since-last-post, reply latency, tag breadth-of-expertise vs depth-on-tag.
- **Predicting Question Quality on Stack Overflow with Neural Networks** (https://arxiv.org/pdf/2404.14449, Apr 2024): 80% accuracy on quality classification.
- **An empirical assessment of best-answer prediction models in technical Q&A sites** (https://arxiv.org/pdf/1903.09522): the canonical pre-LLM baseline.
- **Towards dynamic interaction-based model** (https://arxiv.org/pdf/1801.03904): dynamic reputation captures past activity, cumulative knowledge, **inactivity penalties**.

Key insight: a static metric like total karma drastically underweights **recent quality** and overweights **historical noise**. Dynamic models with explicit inactivity decay outperform.

### 2. Reddit-specific signals — what still works in 2026

- **Sockpuppet/karma-manipulation detection** (https://egrove.olemiss.edu/cgi/viewcontent.cgi?article=2552&context=hon_thesis, https://arxiv.org/pdf/1703.03149): timing-pattern correlation across accounts, comment-burst detection, lexical fingerprinting, posting-time circadian-pattern matching.
- Reddit's own internal **behavioral-fingerprinting** layer (rolled out 2025): keystroke rhythm, voting patterns, time-on-site. Not exposed externally.
- For us: we can't observe keystrokes, but we **can** observe posting timestamps, lexical fingerprints (n-gram + style embedding), reply graph topology, and burst timing. These give a decent sockpuppet score even on archival dumps.
- **Reddit CQS (Contributor Quality Score)** model (https://redaccs.com/reddit-cqs-guide/, 2026): Reddit's public framework weights account age + karma quality + on-topic ratio + community-specific participation. Use as a structural reference for our weighting.

### 3. Author profiling / expertise inference for medical/education forums

- **Can Anonymous Posters on Medical Forums be Reidentified?** (https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3806358/): canonical paper showing stylometric features alone can re-identify medical-forum authors. Implication for us: per-user style embedding is a strong identity signal.
- **Zero and Few-shot Learning for Author Profiling** (https://arxiv.org/pdf/2204.10543): zero-shot prompts predict age/gender/expertise from text alone. In 2026 this generalizes well with Claude Haiku 4.5 prompted with rubric.
- **Active inference strategy for prompting reliable LLM responses in medical practice** (https://www.nature.com/articles/s41746-025-01516-2): expert-style prompting yields more conservative, more reliable responses. Relevant for our extraction prompt-engineering.
- **The Growing Impact of NLP in Healthcare and Public Health** (Jerfy/Selden/Balkrishnan 2024, https://journals.sagepub.com/doi/10.1177/00469580241290095): LDA on 84K+ Reddit posts × 1M+ comments from 4 countries. Method baseline for large-scale forum NLP.

### 4. BERTopic 2.x + CDLib in 2025

(Already covered in R-007b §3 — same libraries, same conclusions. BERTopic 0.17 is current; CDLib remains the meta-library for opinion clustering. The Reddit-polarization Louvain-with-sparsification paper https://arxiv.org/html/2510.27467v1 is the most copy-able 2025 pattern.)

### 5. Time-windowed consensus

The community's view of "the best schools for X" in 2018 is not its view in 2024. Treatment:

- Bucket opinion edges into 6-month or 1-year time windows (per the bitemporal `t_valid` field).
- Re-run the consensus-cluster pipeline (R-007b §3) per window.
- Store cluster outputs as **versioned consensus nodes** (`Consensus[topic=X, window=2018-H2]`).
- Queries can ask "consensus on X as of 2018" or "drift between 2018 and 2024" → simple time-windowed traversal.

Combined with the per-edge-type half-life decay (R-007b §2), this gives us both **soft decay** (older opinions count less in the *current* consensus) and **hard versioning** (older consensus snapshots remain queryable as history).

### 6. Outlier preservation — the low-karma-but-right problem

Empirical evidence (https://www.researchgate.net/publication/316534762_Identifying_outlier_opinions_in_an_online_intelligent_argumentation_system) plus signed-network polarized-community literature: **never delete outlier opinions; tag them and surface them on demand**. Specifically:

- Tag minority-camp claims `Status: Anomaly` (not `Status: Invalidated`) — they remain queryable.
- Track **post-hoc validation**: if a later L1/L2 source confirms a previously-tagged-anomaly claim, retroactively increment that user's credibility score (`prescient_correct` counter).
- Surface tagged-anomaly claims in `query_graph` when `include_outliers=True` is passed.
- Stance + intensity (not just stance polarity) improves outlier surfacing (cited paper above).

This is the V1 mechanism for handling the "Reddit's policy-change rumor that ADEA hasn't published yet" scenario — the rumor flows in as an L5 anomaly, surfaces a `research_need` to the crawler, gets confirmed by L2, retroactively promoted, and the user(s) who posted it get a `prescient_correct` credit.

### 7. Draft user-credibility rubric (V1 deliverable)

Per-user score, range 0..1, computed monthly. Features and proposed weights:

| Feature | Source | Weight | Range / form | Notes |
|---|---|---|---|---|
| `account_age_days` | Reddit/SDN metadata | 0.10 | `min(age/730, 1.0)` (cap at 2 yr) | Age past 2 yr no longer adds; matches Reddit CQS findings. |
| `total_post_count` | metadata | 0.05 | `log10(1+n)/4` | Diminishing returns; matters but not linear. |
| `total_upvote_to_post_ratio` | metadata | 0.10 | clipped [-5, +50] → [0, 1] | Upvotes per post, robust to spammers. |
| `on_topic_ratio` | computed from topic clusters | 0.20 | fraction of posts in dental/applicant subreddit set | Strongest signal of relevant expertise. |
| `reply_quality` | gilded count + reply-to-post-ratio | 0.10 | log-scaled | Engagement quality, not just volume. |
| `temporal_activity_distribution` | timestamp entropy | 0.05 | Shannon entropy / max | Spread across time vs burst. Sockpuppet inverse signal. |
| `stylometric_consistency` | char-ngram embedding variance | 0.05 | inverse variance, capped | High variance ≈ shared account. |
| `topic_expertise_specificity` | inverse Gini over topic-tag distribution | 0.10 | normalized | A deeply-on-topic user beats a generalist. |
| `prescient_correct_count` | L1/L2 post-hoc validation | 0.10 | `log10(1+n)/2` | The low-karma-but-right bonus. |
| `sockpuppet_penalty` | timing + stylometric correlation across accounts | 0.10 | subtracted | Negative-only; can drop the score by up to 0.10. |
| `inactivity_decay` | days since last post | multiplicative | `(1/2)^(days_since_last/365)` | Half-life of 1 year on the whole score, per Stack Overflow dynamic-reputation literature. |

Then `user_credibility = clamp01(Σ(weight_i × feature_i)) × inactivity_decay`.

This is hand-set. The right next step is **logistic regression** with HITL-labeled "expert vs not" labels on a 200-user sample once we have one — that gives us learned weights and replaces the hand-set table by V1.1.

### 8. Opinion-clustering pipeline (V1 deliverable)

```
Inputs: per-topic claim set + user_credibility scores + bitemporal edge timestamps.
Steps:
 1. Embed each claim with BGE-small (768d).
 2. Build claim-claim graph: cosine top_k=15 + extracted SUPPORTS/CONTRADICTS edges (signed).
 3. Statistical-validation sparsification (per Reddit-polarization 2025 paper).
 4. Per time-window (1 year):
    a. Run signed-graph community detection (γ-polarity neural / signed-Leiden).
    b. Weight each node by author's user_credibility × temporal_decay(half_life=topic-specific).
    c. Largest weighted camp → "consensus"; smaller camps → tagged Anomaly.
    d. BERTopic-summarize the central claim of each camp (Claude Haiku 4.5 with cached prompt).
 5. Write Consensus[topic, window] node with provenance pointers to all member claims.
 6. Cross-window drift: link Consensus[topic, window_n] -DRIFTED_TO-> Consensus[topic, window_n+1]
    with a magnitude property.
```

---

## Summary of recommendations (one per stream)

- **R-007a**: adopt Wikidata's rank+references+qualifiers semantics; build entity resolution as **BGE-small NN-blocking → DITTO/DistilBERT reranker** against the 1K-canonical L1 list, with auto/HITL/reject thresholds from R0; defer Splink to V2; do NOT use any off-the-shelf GraphRAG library's trust model — none surface multi-tier source trust as a first-class concept (this is genuinely under-published).
- **R-007b**: borrow Graphiti's bitemporal edge model wholesale (`t_valid_from/to`, `t_ingest_from/to`); apply **HALO-style half-life decay per edge type** with the hand-set V1 table above; use **signed-graph community detection** (not vanilla Leiden) on the opinion layer; LLM-as-judge only for same-tier same-year tie-breaks with cross-vendor calibration — everything else is deterministic rules or HITL.
- **R-007c**: build the 10-feature, hand-weighted user-credibility rubric above; replace with logistic regression at V1.1 once HITL labels exist; preserve outliers via `Status: Anomaly` (never delete); track `prescient_correct` to handle the low-karma-but-right case; time-window the consensus snapshots and link them with `DRIFTED_TO` edges so drift is queryable.

---

## Open questions surfaced (feed into unresolved-questions.md)

- Q-23: what is the per-edge-type half-life table? Current proposal is hand-set; needs HITL calibration on a sample.
- Q-24: which signed-graph community-detection implementation? γ-polarity neural (newer, more code work) vs signed-Leiden (older, simpler). Suggest signed-Leiden V1, γ-polarity V2.
- Q-25: where does the per-user style embedding live — same Kùzu instance or a separate vector index?
- Q-26: when do we re-train the DITTO reranker? Monthly? On HITL-label arrival?
- Q-27: HMAC-signed tool receipts for the outbound crawler MCP — worth implementing in V1 or defer?
