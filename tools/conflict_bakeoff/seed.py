"""L1-grounded seed conflict set for the ADR-026 bake-off.

A constructed-but-grounded seed (the bootstrap until real HITL labels accumulate,
per ADR-026): real dental-admissions predicates, L1 = ADEA ground truth, with the
contradiction patterns that matter — stale-official-vs-fresh-corroborated-minority,
corroborated-but-wrong majority, and same-tier corroboration tie-breaks.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ClaimInput:
    value: str
    source_tier: str          # L1..L5
    t_valid_year: int
    corroborations: int = 1   # independent sources asserting this value
    credibility: float = 0.5


@dataclass(frozen=True)
class ConflictCase:
    case_id: str
    subject: str
    predicate: str
    ground_truth: str
    claims: tuple[ClaimInput, ...]
    minority_correct: bool = False  # truth comes from a lower tier than a competing claim
    note: str = field(default="")


# now = 2026 for the bake-off.
SEED: tuple[ConflictCase, ...] = (
    ConflictCase(
        case_id="C1-l1-authoritative",
        subject="school:nyu", predicate="tuition_resident", ground_truth="94108",
        claims=(
            ClaimInput("94108", "L1", 2024, corroborations=1, credibility=1.0),
            ClaimInput("85000", "L5", 2024, corroborations=1, credibility=0.5),
        ),
        note="Current L1 fact vs a lone wrong L5 rumor → L1 (both methods should agree).",
    ),
    ConflictCase(
        case_id="C2-stale-l1-fresh-corroborated-minority",
        subject="school:harvard", predicate="casper_required", ground_truth="yes",
        claims=(
            ClaimInput("no", "L1", 2021, corroborations=1, credibility=1.0),   # stale official
            ClaimInput("yes", "L5", 2025, corroborations=3, credibility=0.6),  # fresh, corroborated, CORRECT
        ),
        minority_correct=True,
        note="Policy changed: a fresh corroborated L5 correction is right; deterministic "
             "L1-clash buries it. THE ADR-021/026 minority-correct case.",
    ),
    ConflictCase(
        case_id="C3-corroborated-wrong-majority-vs-l1",
        subject="school:ucla", predicate="tuition_resident", ground_truth="0",
        claims=(
            ClaimInput("70000", "L5", 2025, corroborations=3, credibility=0.5),  # popular wrong rumor
            ClaimInput("0", "L1", 2024, corroborations=1, credibility=1.0),      # ADEA: $0 resident (public)
        ),
        note="Corroborated-but-wrong L5 majority must NOT beat current L1 (majority ≠ truth).",
    ),
    ConflictCase(
        case_id="C4-same-tier-corroboration-breaks-tie",
        subject="school:michigan", predicate="interview_format", ground_truth="MMI",
        claims=(
            ClaimInput("MMI", "L5", 2025, corroborations=3, credibility=0.5),
            ClaimInput("traditional", "L5", 2025, corroborations=1, credibility=0.5),
        ),
        note="Same tier + year + credibility: deterministic step-3 ties → HITL; "
             "corroboration should break it toward MMI.",
    ),
    ConflictCase(
        case_id="C5-recency-same-tier",
        subject="school:penn", predicate="tuition_resident", ground_truth="91000",
        claims=(
            ClaimInput("78000", "L5", 2019, corroborations=2, credibility=0.5),  # stale
            ClaimInput("91000", "L5", 2025, corroborations=1, credibility=0.5),  # fresh, correct
        ),
        minority_correct=True,
        note="Fresh single L5 vs stale corroborated L5 — recency should win (HALO decay).",
    ),
    ConflictCase(
        case_id="C6-l1-fresh-vs-stale-l5",
        subject="school:bu", predicate="dat_avg", ground_truth="21",
        claims=(
            ClaimInput("21", "L1", 2024, corroborations=1, credibility=1.0),
            ClaimInput("19", "L5", 2020, corroborations=2, credibility=0.5),
        ),
        note="Fresh L1 vs stale corroborated L5 → L1 (both should agree).",
    ),
    ConflictCase(
        case_id="C7-fresh-corroborated-l5-vs-stale-l2",
        subject="school:tufts", predicate="program_requirement", ground_truth="casper",
        claims=(
            ClaimInput("no_casper", "L2", 2021, corroborations=1, credibility=0.8),  # stale official-ish site
            ClaimInput("casper", "L5", 2025, corroborations=4, credibility=0.6),     # fresh, heavily corroborated
        ),
        minority_correct=True,
        note="Stale L2 site vs fresh heavily-corroborated L5 — corroboration+recency should win.",
    ),
    ConflictCase(
        case_id="C8-uncorroborated-same-tier-tie",
        subject="school:columbia", predicate="interview_format", ground_truth="MMI",
        claims=(
            ClaimInput("MMI", "L5", 2025, corroborations=1, credibility=0.5),
            ClaimInput("panel", "L5", 2025, corroborations=1, credibility=0.5),
        ),
        note="Genuine tie (no corroboration/recency signal) — both methods should abstain; "
             "neither is expected to be 'correct' deterministically.",
    ),
)
