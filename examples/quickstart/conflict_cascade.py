"""Walk the conflict cascade with the real `ConflictResolver` on fictional claims.

No API keys: the LLM judge and the web verifier are simply absent here, so anything the
deterministic steps cannot settle is escalated to a human — which is exactly what the engine
does in production when those collaborators are unavailable.

Run:  python examples/quickstart/conflict_cascade.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.conflict.resolver import Claim, ConflictResolver

SUBJECT = "school:marlowe_university_college_of_dentistry"


def year(y: int) -> tuple[datetime, datetime]:
    return datetime(y, 1, 1, tzinfo=UTC), datetime(y, 12, 31, tzinfo=UTC)


def claim(cid: str, value: float, tier: str, y: int, credibility: float, ref: str) -> Claim:
    start, end = year(y)
    return Claim(
        claim_id=cid, subject_id=SUBJECT, predicate="tuition_resident", object_value=value,
        source_tier=tier, rank="preferred" if tier == "L1" else "normal", references=[ref],
        t_valid_from=start, t_valid_to=end, credibility=credibility,
    )


OFFICIAL_2025 = claim("official:2025", 47_800, "L1", 2025, 1.00, "dump:reference_2024-25")
FORUM_2025_WRONG = claim("forum:p03-repeated", 30_000, "L5", 2025, 0.30, "reddit_post:p03")
FORUM_2019 = claim("forum:c04", 30_000, "L5", 2019, 0.40, "reddit_comment:c04")
FORUM_2019_OTHER = claim("forum:old-thread", 33_000, "L5", 2017, 0.40, "reddit_post:older")
NEWBIE_2025 = claim("forum:newbie", 52_000, "L5", 2025, 0.15, "reddit_post:x1")
VETERAN_2025 = claim("forum:veteran", 48_000, "L5", 2025, 0.85, "reddit_post:p09")
PEER_A_2025 = claim("forum:peer-a", 46_000, "L5", 2025, 0.50, "reddit_post:x2")
PEER_B_2025 = claim("forum:peer-b", 49_500, "L5", 2025, 0.50, "reddit_post:x3")

CASES = [
    ("A forum post repeats an old number; the official sheet disagrees",
     FORUM_2025_WRONG, [OFFICIAL_2025]),
    ("Two community claims about DIFFERENT years",
     FORUM_2019, [FORUM_2019_OTHER]),
    ("Same year, same tier — but one author has a far better track record",
     NEWBIE_2025, [VETERAN_2025]),
    ("Same year, same tier, equally credible authors, and no judge available",
     PEER_A_2025, [PEER_B_2025]),
]


def main() -> int:
    resolver = ConflictResolver()  # judge + web verifier intentionally absent (keyless demo)
    for title, new, existing in CASES:
        outcome = resolver.reconcile(new, existing)
        winner = outcome.winning_claim.claim_id if outcome.winning_claim else "—"
        print(f"\n{title}")
        print(f"  new      : {new.claim_id:<22} {new.object_value:>8,.0f}  ({new.source_tier}, {new.t_valid_from:%Y})")
        for c in existing:
            print(f"  existing : {c.claim_id:<22} {c.object_value:>8,.0f}  ({c.source_tier}, {c.t_valid_from:%Y})")
        print(f"  → {outcome.status.value}   winner: {winner}")
        print(f"    {outcome.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
