# L1 Official Source Registry — U.S. & Canadian Dental Education

> **Purpose.** The definitive list of OFFICIAL publishers whose data qualifies for the
> platform's L1 (ground-truth) tier. Anything not from these sources is at best
> forum-consensus (L5) and must be labeled as such. Built by adversarially-verified
> deep research (3-vote refutation per claim), 2026-06-10. Round 1: 25/25 claims
> survived. Round 2 (residency match + international pathway) appended below.
> Round 3 (ADAT, INBDE/JCNDE+DLOSCE, U.S. clinical licensure, state-board umbrella,
> HRSA, and the Canadian stack) verified by direct primary-source fetch 2026-06-11.
>
> **Verification key:**
> - ✅ = claim survived **3-vote** adversarial verification with live fetches (rounds 1–2, 2026-06-10).
> - ☑ = **primary-source verified** by single direct fetch of the official site (round 3, 2026-06-11).
>   Strong (every fact read off the operator's own page) but not triple-refuted — re-run through
>   the deep-research harness before treating any ☑ row as bulletproof.
> - No mark = pending verification — do not ingest as L1 until verified.
>
> **Round-3 corrected three of my priors** (why verification is non-optional): the NDEB Canada
> exams are now AFK/ACJ/**NDECC** (not "ACS"); CDCA-WREB-CITA rebranded to **The American Board
> of Dental Examiners** (adextesting.org); and **aadb.org is the American Association of the
> *DeafBlind*** — the dental boards body is a different site. Each would have poisoned L1.

## Ingestion rules (apply to every source)

- **No source offers an API.** Ingestion = scrape the landing page for current file
  hrefs → download XLSX/PDF. ADEA file URLs carry `sfvrsn` version params — never
  hardcode file URLs; always resolve from the landing page.
- **Tag cadence + cycle on every fact** (`cycle_year`, `retrieved_date`). Most series
  are annual with 1–2 year lag; "current" ≠ real-time.
- **Licensing:** ADEA Trends = non-commercial share-alike (constraint for a commercial
  platform — needs counsel review or first-party recomputation). ADEA Official
  Guide/Explorer = paywalled, no redistribution rights verified. ADA HPI/CODA survey
  files = free downloads; redistribution terms unverified.

---

## Domain 1 — Predoctoral admissions funnel (applicants/enrollees) ✅

| Field | Value |
|---|---|
| Source | **ADEA "U.S. Dental School Applicants and Enrollees"** annual series |
| Operator | American Dental Education Association (ADEA) |
| URL | adea.org/home/publications/research-and-data/applicants-enrollees-and-graduates |
| Authoritative for | National applicant/enrollee counts, demographics, applicant→enrollee funnel (first-party AADSAS + TMDSAS records = full accredited-pool coverage incl. Texas) |
| Cadence | Annual, spring after each entering class (2025 class → Apr 7 2026) |
| Access | **Free XLSX, no auth** (verified by anonymous download). ADEA Data Portal dashboards = member-gated. No API |
| Notes | Also peer-reviewed annually in J Dental Educ. ADA HPI is co-authoritative for *graduates/total enrollment*; ADEA owns the *admissions funnel* |

## Domain 2 — Accreditation & program existence ✅

| Field | Value |
|---|---|
| Source | **CODA "Search for Dental Programs"** directory + CODA publications |
| Operator | Commission on Dental Accreditation (ADA-housed; **sole USDE-recognized accreditor**) |
| URL | coda.ada.org/find-a-program |
| Authoritative for | Program existence + accreditation status: 1,440 accredited programs (Nov 2024): 75 predoctoral, 780 advanced, 585 allied |
| Cadence | Live directory; counts drift across snapshots (75 schools fall-2024 vs 78 per HPI 2026) |
| Access | Free directory; no API |
| Notes | This is the registry *beneath* ADEA's own publications — ADEA cites CODA |

## Domain 3 — Tuition, fees, admissions policies (per school) ✅

| Field | Value |
|---|---|
| Source | **ADA HPI / CODA Survey of Dental Education — Report 2 (Tuition, Admission, Attrition)** |
| Operator | ADA Health Policy Institute (official collector for CODA; mandatory-response census) |
| URL | ada.org/resources/research/health-policy-institute/dental-education |
| Authoritative for | Tuition + fees + admissions criteria of every CODA-accredited U.S. dental school |
| Cadence | Annual (2025-26 current) |
| Access | Free XLSX/PDF; no API |
| Notes | Cited by CDC/NCHS as the federal source. For a school's *current-cycle* requirements, the school admissions office remains the operational authority — Report 2 is the canonical aggregated dataset. **This is the upgrade path for our single-cycle tuition L1.** |

## Domain 4 — Residency/advanced-education program data ✅

| Field | Value |
|---|---|
| Source | **ADA HPI / CODA Survey of Advanced Dental Education** |
| Operator | ADA Health Policy Institute |
| URL | ada.org/resources/research/health-policy-institute/dental-education |
| Authoritative for | All 14 CODA disciplines (AEGD, GPR + 12 specialties incl. dental anesthesiology, orofacial pain, oral medicine): enrollment, graduates, demographics, tuition, **stipends**, international dental graduates |
| Cadence | Annual; free XLSX archive 2015-16 → 2024-25 |
| Access | Free; no API |

## Domain 5 — Application services (predoctoral) ✅

| Field | Value |
|---|---|
| Source | **ADEA AADSAS** (+ **TMDSAS** for Texas-resident → Texas public schools) |
| Operator | ADEA (AADSAS); Texas Medical & Dental Schools Application Service (TMDSAS) |
| URL | adea.org/godental/Apply/apply-to-adea-aadsas · tmdsas.com |
| Authoritative for | Application requirements, official cycle dates (2026-27: opens May 12 2026, closes Feb 5 2027) |
| Cadence | Annual cycle — dates are cycle-scoped, must refresh yearly |
| Access | Public info pages free; applicant data flows into the ADEA series (Domain 1) |
| Notes | A complete national picture = AADSAS + TMDSAS. Foreign-trained dentists apply via **ADEA CAAPID** (Domain 9, round 2) |

## Domain 6 — Per-school admissions/cost reference (incl. Canada) ✅

| Field | Value |
|---|---|
| Source | **ADEA Official Guide to Dental Schools** + **ADEA Dental School Explorer** |
| Operator | ADEA |
| URL | adea.org/home/publications/Books-and-Guides/officialguide |
| Authoritative for | Per-school applicant/entering-class stats (mean DAT/GPA), costs, timelines, prereqs, shadowing, IDG program info — U.S. **and Canadian** schools |
| Cadence | Explorer refreshes each spring (data lags ~1–2 yr); PDF biennial (next 2027) |
| Access | **Paid**: $35 PDF + 1-yr Explorer; Explorer alone $25/yr; login-gated, no API, no verified redistribution rights |
| Notes | Per-school figures are school-reported |

## Domain 7 — Sector trends & education debt ✅

| Field | Value |
|---|---|
| Source | **ADEA Trends in Dental Education** (2024-25 current; archive to 2015-16) |
| Operator | ADEA |
| URL | ADEA.org/ADEATrends |
| Authoritative for | Programs, applicants, enrollment, **education debt**, faculty trends |
| Cadence | Annual |
| Access | Free PDF/interactive, no auth. **License: non-commercial share-alike with citation** — flag for commercial use |

## Domain 8 — DAT (Dental Admission Test) ✅

| Field | Value |
|---|---|
| Source | **ADA DAT program** (Candidate Guide, DAT User Manual, score concordance) |
| Operator | ADA Council on Dental Education and Licensure (governing) + ADA Dept. of Testing Services (operating); **Prometric = delivery vendor only** |
| URL | ada.org/education/testing/exams/dental-admission-test-dat |
| Authoritative for | DAT policy, eligibility, fees, content, score norms/percentiles |
| Cadence | Guides annual; norms with User Manual updates |
| Access | Free PDFs; scores in DTS Hub (candidate-gated); no API |
| **Critical ingestion rule** | **Score-scale break 2025-03-01**: 1–30 scale → 200–600 (10-pt increments, no passing score). Both scales remain in circulation. **Every ingested DAT score must be tagged with its scale**; official old→new concordance: ADA.org/DATConcordanceTable (built from 30K+ dual-scored attempts, per-subtest). Our 15-yr forum corpus is almost entirely old-scale. |
| Notes | Do NOT generalize the vendor: ADA's **ADAT and NBDHE run on Pearson VUE**, not Prometric. **Canadian DAT is a separate exam run by the CDA** (Domain 14) |

---

## Domain 9 — Residency applications (ADEA PASS) ✅

| Field | Value |
|---|---|
| Source | **ADEA PASS** (Postdoctoral Application Support Service) |
| Operator | ADEA (on Liaison's CAS platform) |
| URL | adea.org/home/application-services/apply-to-advanced-programs/adea-pass-applicants |
| Authoritative for | The residency **application layer** (requirements, cycle dates). **Publishes NO statistics** — zero match/volume data on its pages |
| Cadence | Annual: opens 2nd Wednesday of May, closes 2nd Friday of February (2026-27: May 13 → Feb 12) |
| Access | Applicant-paid ($199 first program, $92 each additional); info pages free; no API |
| Notes | "Most, but not all" Match programs collect applications via PASS — PASS ≠ the Match |

## Domain 10 — Residency match statistics (the Dental Match) ✅

| Field | Value |
|---|---|
| Source | **Postdoctoral Dental Matching Program ("the Dental Match")** statistics |
| Operator | **National Matching Services Inc. (NMS)** — on behalf of 8 specialty sponsors (AAPD, AAOMS, AAO, AAP, ASDA, ASDA-anesth, SCDA, ACP). **Not ADEA, not ADA** (endorsers only) |
| URL | natmatch.com/dentres/statistics.html |
| Authoritative for | THE match statistics: applicant + program volumes, positions offered/filled, matched/unmatched by specialty across **9 program types** (AEGD, US GPR, **Canadian GPR**, OMS, Ortho, Pedo, Perio, Pros, Dental Anesthesiology). Endodontics is NOT in the Match; data covers Match-filled positions only |
| Cadence | Posted on each phase's Match Results Day (2027 positions: Nov 23 2026 Phase I, Jan 20 2027 Phase II). Archives 2022–2026, graphs to 2016. **Phase composition changed for 2027** (GPR/AEGD → Phase I) |
| Access | **Free PDFs, no login** (verified by unauthenticated fetch); no API |
| Example granularity | 2026-27 Phase I: 1,354 applicants, 680 matched (Ortho 341, Perio 129, Pros 116, CAN-GPR 60, DA 34), 674 unmatched |

## Domain 11 — International dentists: CAAPID + credential evaluation ✅

| Field | Value |
|---|---|
| Source | **ADEA CAAPID** (Centralized Application for Advanced Placement for International Dentists) + Program Finder |
| Operator | ADEA (Liaison CAS delivery) |
| URL | adea.org/home/application-services/internationally-educated-dentists · programs.adea.org/CAAPID/programs |
| Authoritative for | U.S. advanced-standing DDS/DMD programs **that participate in CAAPID** (45 programs as of 2026-06-10) |
| Cadence | Annual cycle Mar→Jan (2026-27: Mar 5 2026 → Jan 29 2027) |
| Access | Program Finder free; application paid + login-gated; no API |
| **Refuted claim (0–3)** | CAAPID is NOT the single channel for international dentists — some advanced-standing programs accept direct applications. **Full pathway coverage requires per-school data** — partially a crowd/per-school domain by design |
| Credential evaluation | **Exactly two evaluators accepted at CAAPID level: WES and ECE** (Course-by-Course, $199 at ECE); per-program preferences vary (e.g., NYU/Penn = ECE only). Scoped to CAAPID — state boards/NDEB have separate rules |

---

---

## Domain 12 — ADAT (Advanced Dental Admission Test) ☑

| Field | Value |
|---|---|
| Source | **ADA ADAT** (Candidate Guide + 2025 ADAT Users Guide) |
| Operator | ADA **Department of Testing Services** (same DTS that runs the DAT); **Pearson VUE = delivery vendor** (NOT Prometric — DAT uses Prometric, ADAT/NBDHE use Pearson VUE) |
| URL | ada.org/education/testing/exams/advanced-dental-admission-test-adat |
| Authoritative for | ADAT policy, eligibility, score scales + **frequency distributions** (in the ADAT Users Guide) |
| Cadence | Application window **March 1 – August 31** annually; testing in designated Pearson VUE windows |
| Access | Free guide PDFs; scores candidate-gated; no API |
| Notes | Used by some (not all) advanced-education programs; **acceptance is program-by-program** — no central list of which residencies require it. Base fee + 50% partial waivers exist (exact fee in the Candidate Guide PDF) |

## Domain 13 — INBDE (national board exam) ☑

| Field | Value |
|---|---|
| Source | **JCNDE INBDE** (Joint Commission on National Dental Examinations) |
| Operator | **JCNDE**, housed at the ADA (jcnde.ada.org); operates with the ADA Dept. of Testing Services |
| URL | jcnde.ada.org/en/inbde |
| Authoritative for | THE U.S. national board licensure exam (replaced NBDE Parts I & II). Official pass rates + technical reports are JCNDE-published |
| Cadence | Year-round at Prometric; reports/pass-rates annual |
| Access | Free guides/reports; scores candidate-gated; no API |
| Notes | INBDE ≠ clinical exam — it is the cognitive/written board. Clinical competency is a **separate** layer (Domain 14) |

## Domain 14 — U.S. clinical licensure exams (two competing owners) ☑

| Field | Value |
|---|---|
| Source A | **ADEX exams** — operator **The American Board of Dental Examiners** (the merged **CDCA-WREB-CITA**, rebranded 2025-26) |
| URL A | adextesting.org (cdcaexams.org now redirects here) |
| Authoritative for A | ADEX Dental, ADEX Dental Hygiene, Dental Therapy, EFDA, sedation/anesthesia exams. **Accepted in most U.S. jurisdictions** — exceptions: **DE + NY** don't accept ADEX Dental; **DE + NE** don't accept ADEX Dental Hygiene (per its own portability maps) |
| Source B | **DLOSCE** (Dental Licensure Objective Structured Clinical Examination) — operator **ADA / JCNDE** (with DTS; Prometric centers) |
| URL B | jcnde.ada.org/en/dlosce |
| Authoritative for B | A manikin/OSCE clinical exam accepted in **8 states** (AK partial, AZ, CO, IN, IA partial, KY, OR, WA) "in full or partial fulfillment of clinical examination requirements" |
| **Unconfirmed** | A reported "April 2026 ADA-ADEX DLOSCE agreement" does **NOT** appear on JCNDE's official page — treat as rumor until a primary source confirms it |
| Conclusion | **No single authority** for "which clinical exam each state accepts" — ADEX and DLOSCE each publish their own acceptance map; the **state board** is the reconciling authority (see Domain 15) |

## Domain 15 — State licensure: umbrella references vs ground truth ☑

| Field | Value |
|---|---|
| Aggregator (consumer-facing) | **ADA Dental Licensure Dashboard** — interactive per-state maps: initial licensure, CE/renewal, licensure-by-credential, specialty, accepted clinical exams |
| URL | ada.org/resources/careers/licensure (+ /dental-licensure-by-state-map) |
| Board-facing infrastructure | **AADB** (American Association of Dental Boards) — runs the **Clearinghouse** (disciplinary/investigative data on thousands of licensees) + the **Licensure Repository** for the Dentist & Dental Hygienist **Compact** |
| AADB URLs | aadb.memberclicks.net/clearinghouse · **aadbcompact.org** (NOT aadb.org — that's the Assoc. of the DeafBlind) |
| Cadence | ADA maps updated "based on available information"; AADB clearinghouse continuous |
| **Conclusion** | **No single authoritative per-state requirements source.** ADA's own page: "Individuals... are strongly urged to consult with the respective state board of dentistry." **The 50+ individual state boards are the ground truth**; ADA map = navigation aid, AADB = board-side data exchange |

## Domain 16 — Workforce & shortage data (HRSA) ☑

| Field | Value |
|---|---|
| Source | **HRSA Bureau of Health Workforce (BHW)** + data.hrsa.gov |
| URL | bhw.hrsa.gov/data-research/projecting-health-workforce-supply-demand · data.hrsa.gov (HPSA dashboards) |
| Authoritative for | **Dental Health Professional Shortage Areas (HPSAs)** (Dec 31 2025: 63.7M people in dental HPSAs, 10,744 dentists needed to clear) + **oral-health workforce supply/demand projections** (demand > supply by ~2030; 46% nonmetro shortage by 2038). 34+ federal programs key eligibility off HPSA designations |
| Cadence | HPSA designations continuous; projections periodic |
| Access | Free dashboards + PDFs; some data via data.hrsa.gov tools |
| **Scope caveat** | HRSA is authoritative for **workforce/shortage**, NOT for **dental-education debt** — that remains **ADEA Trends / ADA-HPI** (Domains 7, 3). For program-level debt cross-checks, **Federal Student Aid College Scorecard** (collegescorecard.ed.gov, debt by CIP code) is a federal candidate — *not yet adversarially verified; do not treat as L1 until checked* |

## Domain 17 — Canada: international-dentist equivalency (NDEB) ☑

| Field | Value |
|---|---|
| Source | **NDEB Equivalency Process** (National Dental Examining Board of Canada) |
| Operator | NDEB |
| URL | ndeb-bned.ca/en/equivalency-process |
| Authoritative for | The path for graduates of **non-CDAC-accredited** programs toward Canadian certification. **Current exams: AFK® (Assessment of Fundamental Knowledge), ACJ® (Assessment of Clinical Judgement), NDECC®** — ⚠️ **NOT the old "ACS / Assessment of Clinical Skills"** (the process was restructured; NDECC replaced ACS) |
| Cadence | Scheduled exam sittings; see NDEB calendar |
| Access | Fees per the NDEB Fees page; no API |
| Notes | Gateway to the **NDEB Certification Process**. Canadian-side analogue to the U.S. CAAPID/advanced-standing route but is an **exam-equivalency**, not an application service |

## Domain 18 — Canada: Canadian DAT (CDA) ☑

| Field | Value |
|---|---|
| Source | **Canadian DAT** (Dental Aptitude Test Program) |
| Operator | **Canadian Dental Association (CDA)** — "provided by the CDA to assist dental schools in selecting first-year students" |
| URL | cda-adc.ca/en/becoming/dat (Candidate Guide PDF linked there) |
| Authoritative for | Canadian DAT policy, structure, scores. **Distinct exam from the U.S. ADA DAT** |
| Cadence | Multiple sittings/year (see Candidate Guide) |
| **Critical note** | The **Manual Dexterity Test (soap carving) is CURRENTLY SUSPENDED** per CDA ("because of COVID-19 restrictions and related logistical challenges") — do NOT assume it is administered. Structure differs from U.S. DAT; rely on the CDA Candidate Guide, not prep-company pages |

## Domain 19 — Canada: program accreditation (CDAC) ☑

| Field | Value |
|---|---|
| Source | **Commission on Dental Accreditation of Canada (CDAC / CADC)** — the Canadian counterpart to the U.S. CODA |
| Operator | CDAC |
| URL | **cdac-cadc.ca** (find-a-program directory) — ⚠️ NOT cda-adc.ca (that's the CDA) |
| Authoritative for | Accreditation + existence of Canadian programs: dentistry (DDS/DMD), dental specialty, residency, dental hygiene, dental assisting; also recognizes international oral-health programs |
| Cadence | Live directory; standards periodically revised (90-day consultation Apr 17–Jul 16 2026 on new standards) |
| Access | Free directory; no API |

## Domain 20 — Canada: dental-school applications (NO single source) ☑

| Field | Value |
|---|---|
| Finding | **There is NO single centralized Canadian application service.** It is mixed/per-school |
| Examples | U of Toronto → **UTDAS** (own service) or ADEA AADSAS; Western (Schulich) → **OUAC**; others apply **directly** to each school |
| Authoritative for | Each school's admissions office + its chosen portal is authoritative for its own cycle |
| **Conclusion** | Unlike the U.S. (AADSAS+TMDSAS cover the pool), **Canadian application data is per-school ground truth** — no aggregator to ingest. ADEA AADSAS covers only Canadian schools that opt in |

---

## Domains with NO single authoritative source (per-school / crowd ground truth)

These are **not** failures of research — they are genuinely decentralized. Do not look for an L1
aggregator that does not exist; per-school data is the ground truth (this is where our forum corpus
+ per-school scraping adds the most unique value):

1. **Non-CAAPID U.S. advanced-standing programs** (Domain 11) — some take direct applications.
2. **Which clinical exam each U.S. state accepts** (Domain 14) — ADEX vs DLOSCE each self-report; the state board reconciles.
3. **Per-state licensure requirements** (Domain 15) — the 50+ state boards are the only ground truth; ADA map + AADB are aids.
4. **Canadian dental-school applications** (Domain 20) — UTDAS / OUAC / direct; no central service.
5. **Which residencies require the ADAT** (Domain 12) — program-by-program.
6. **Program-level education debt** (Domain 16) — ADEA/ADA-HPI give sector series; College Scorecard is an unverified federal candidate.
