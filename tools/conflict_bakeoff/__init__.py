"""ADR-026 truth-discovery bake-off (WP5).

Deterministic cascade (current `ConflictResolver`, ADR-006) vs a jointly-estimated
confidence score (source-reliability x recency x corroboration — ADR-026 candidate
(b), reusing `consistency.py` / `ranking.py` / HALO decay) on an L1-grounded seed
conflict set. Metrics: accuracy vs ground truth + minority-correct recall (does it
keep a corroborated correct minority instead of burying it under stale/official
data?). Never mutates L1 — this judges which *value* is current truth, not the L1
node.
"""
