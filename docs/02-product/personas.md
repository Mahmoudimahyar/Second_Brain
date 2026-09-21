# Personas

> Light treatment per `ai_agent_system` mode. Three personas for V1, mapped 1:1 to the V1 user types in `docs/01-core/user-types.md`.

## Persona: Ingestion operator (V1 = Mahyar)

### Description
Founder / lead engineer of the project. Comfortable with Python, ML, ops. Time-constrained: builds in evenings + weekends + focused sprints. Owns every architectural call.

### Goals
- Run a clean L5 sweep over r/DentalSchool against L1 ADEA and get a usable graph in days, not months.
- Predictable, capped API spend.
- A graph that downstream agents (and downstream products like DentistJourney) can query without lying.
- Trivial vendor switching (he asked for this explicitly in R4).

### Pain points
- Past GPT-4o-mini extraction attempt didn't reach his accuracy bar (R0 brainstorm-dump).
- Hardware ceiling: GTX 1080, 8 GB VRAM (Pascal). Can't run a serious local 8B LLM workhorse.
- Inflexible vendor SDKs that lock him into one provider.
- LLM hallucinations on noisy forum text.

### Usage triggers
- New data drop arrives → run ingestion.
- Hypothesis to test (e.g., "did NYU's DAT cutoff drift over 5 years?") → run `query_graph`.
- Re-prompt or model upgrade → re-sweep with cache hits keeping cost near-zero.

### Objections
- "Won't this take months?" — V1 slice estimated 3 focused weeks after gates pass.
- "Won't this cost thousands?" — V1 slice under $25 per `tech-stack.md` cost envelope.
- "What if Anthropic raises prices?" — gateway fallback chain (Haiku → Gemini 2.5 Flash-Lite → GPT-4o-mini) keeps the system portable.

## Persona: HITL reviewer (V1 = Mahyar; V1.x+ = contracted dental-admissions expert)

### Description
Domain expert (or Mahyar acting as one) who arbitrates borderline cases. In V1 the reviewer interacts via CLI + YAML files; in V2 via a web UI.

### Goals
- See full context for a borderline case in one screen (mention + thread excerpt + nearest canonical candidates + ER scores).
- Make a defensible accept / reject / new-alias / new-type call in < 1 minute per item.
- Confident that decisions are audit-logged and recoverable.

### Pain points
- Ambiguous evidence (e.g., a mention of "Penn Dental" in a thread about both UPenn and the broader Pennsylvania dental community).
- Slow CLI workflow when queue depth > 100.
- Reviewer burnout on long sessions.

### Usage triggers
- Queue depth ≥ 50 items → batch session.
- Daily / weekly cadence as Mahyar decides (pending Q-016 HITL hours/week answer).

### Objections
- "Why YAML and not a web UI?" — V1 keeps scope tight; web UI in V2.
- "How do I know my decision propagates correctly?" — every `hitl commit` writes an audit-log row + updates the graph atomically.

## Persona: Downstream human consumer (PM / marketer / internal analyst)

### Description
A product or marketing person (eventually on DentistJourney's team) who needs to derive insights from the graph: "What are the top applicant pain points about NYU in 2024?" / "Which schools shifted DAT cutoffs over 5 years?" / "What interview questions reportedly came up at UCSF in 2023?"

### Goals
- Get a citable answer to a strategic question without reading 1000 forum posts.
- See sources for every claim (L1 vs L5 differentiation visible).
- Trust temporal accuracy (no 2014 advice presented as current).

### Pain points
- Untrusted answers without citations.
- Stale data presented as current.
- Confusion between authoritative ADEA facts and aggregated forum sentiment.

### Usage triggers
- Strategic question raised in product / marketing planning.
- Quarterly review of "applicant top-of-funnel concerns by month."

### Objections
- "Is this making things up?" — every retrieval result carries `references` linking back to source posts/files; citation traceability ≥ 99%.
- "Why is this from 2018?" — bitemporal + HALO decay ranking surfaces fresh first; stale anomalies are explicitly marked.
