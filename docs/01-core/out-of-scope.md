# Out of Scope

These are explicitly NOT part of the current build (V1):

## Deferred to V2

- **Downstream agents** (Mahyar said "you decide" on Q-006 round 1 → Claude's call: V2):
  - Product-management ideation agent (synthesizes pain points from the graph → feature specs).
  - Marketing / SEO content-generation agent (graph → templated blog posts, ~5,000 targeted posts in vision; Instagram carousel sub-agent).
  - Search-verification agent (autonomous web search to verify conflicts with L1 ground truth).
  - Data-analyst agent (proactive query of the graph for high-volume unresolved pain points).
  These are **V2 consumers of the V1 graph**, not parts of V1.
- **External / multi-tenant productization** — V1 ships internal-only. V2 generalizes the source-handler interface for other companies' data dumps (the `developer_tool` posture). V2 also gets a rewritten security model, multi-tenant isolation, customer privacy/ToS handling.
- **Epistemic-engine layers** beyond core retrieval (V2+):
  - Intent clarification before answering (challenge flawed premises).
  - Planning-what-to-gather before answering (ground-truth ladder).
  - Bayesian uncertainty modelling on imperfect data.
  - Cost-aware active data acquisition (surveys, voice-agent phone calls, paid databases).
  - Continuous-learning + catastrophic-forgetting mitigation across changing predictive models.

## Skipped per Mahyar's standing rule (not even for the project itself)

- `docs/02-product/pricing.md`, `positioning.md`, `competitors.md` — never written; the empty scaffold templates were removed (2026-09-20).
- `docs/15-marketing/messaging.md`, `channel-strategy.md`, `content-system.md` — never written; the empty scaffold templates were removed (2026-09-20).
- Customer-segmentation analysis for the tool's go-to-market.
- Brand identity / visual design system for the tool itself.

Reminder: the downstream marketing-content-generation **agent** is a **product feature** that lives in `docs/05-features/*` (when scoped, V2). It is *not* project marketing.

## Out of scope for V1 (slice-level)

- Full 500K-thread extraction. V1 ships one subreddit + ADEA SQL only.
- All five trust tiers in V1. V1 demonstrates L1 + L5; L2-L4 plugins are V1-later or V2.
- Multi-domain anchor (V1 = dental only; other domains are V2 validation of the pluggable interface).
- HITL review UI beyond the minimum needed for the V1 slice (might be CLI + spreadsheet in V1; full web UI V2).
- Streaming / real-time ingestion. V1 = batch. V2 considers streaming.
- Authenticated multi-tenant access; rate limiting; quotas. V1 = local single-user.
- Customer-facing consumer UI (DentistJourney itself is a separate downstream consumer / separate repo).

## Out of scope unless explicitly requested

- Any cloud-deployment plan beyond running locally on Mahyar's workstation in V1.
- GPU upgrade roadmap. V1 must work on GTX 1080 8 GB VRAM.
- Migration plan to a different graph DB later (we lock the V1 choice via ADR; revisit if hits scaling wall).
