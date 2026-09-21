# Decisions — V1.5c

> Extends V1 + V1.5a + V1.5b ADRs. Cross-cutting decisions live in `docs/11-decisions/ADR-*`.

| ID | Decision | Rationale | Status |
|---|---|---|---|
| D-1.5c-1 | Tavily-only web-verify (no Brave) | V1.5-R2 user direction; only `TAVILY_API_KEY` provided | Locked V1.5-R2 |
| D-1.5c-2 | Three-signal combine (A=Tavily QNA + B=paraphrased search + C=extract+2-LLM) | Mirrors V1 ADR-006 three-judge invariant for single-provider verification | Locked ADR-016 v2 |
| D-1.5c-3 | Two-vendor LLM extract-verify (Haiku + Gemini Flash, both required for signal C) | Reuses existing model gateway + ADR-011 cost matrix | Locked |
| D-1.5c-4 | Cost cap default $5 / corpus / sweep | Conservative default; configurable per corpus | Locked V1.5-R1 default; reconfirm at V1.5c kickoff |
| D-1.5c-5 | 7-day cache TTL on web-verify | Most web content is stable within a week | Locked |
| D-1.5c-6 | `team_content_angles` task model = Gemini 2.5 Flash-Lite (default; swappable) | V1.5-R2 user direction; cheap; model gateway makes swap one-line | Locked V1.5-R2 |
| D-1.5c-7 | Per-team rollups pre-computed daily by Prefect flow | Avoids real-time aggregation cost on every page load | Locked |
| D-1.5c-8 | Suggested angles regenerated on every drill-down (cached, not persisted) | Cheap; reproducible via cache; no stale-content risk | Locked |
| D-1.5c-9 | PM + Social + Marketing as three separate dashboards (not a generic configurable one) | V1.5-R1 user choice; tighter per-team UX | Locked |
| D-1.5c-10 | Provider Protocol pluggable; only Tavily ships in V1.5c | V1.6 candidate to add Brave / Firecrawl as fallback | Locked |
| D-1.5c-11 | `WebVerificationAgent` runs inside V1's conflict resolver at step 5 | Architectural alignment with ADR-006 order | Locked |
| D-1.5c-12 | Manual cap reset on cap_hit (no auto-rollover) | Forces operator attention; predictable cost behavior | Locked V1.5-R1 default; reconfirm |
| D-1.5c-13 | All dashboard insights carry citations ≥ 99% | V1 NFR-4 carried to V1.5c | Locked |
| D-1.5c-14 | Angles are LLM-generated drafts with explicit "Draft only" watermark | Prevents accidental external publication of unverified copy | Locked |
