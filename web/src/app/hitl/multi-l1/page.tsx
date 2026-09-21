"use client";

import {
  MultiL1ReviewBody,
  type MultiL1ReviewPayload,
} from "@/components/hitl/MultiL1ReviewBody";
import { ReviewPage } from "@/components/shared/ReviewPage";

export default function MultiL1Review() {
  return (
    <ReviewPage
      title="Multi-L1 collision review"
      description="Two L1 sources disagree on the same fact. Per ADR-014 §5 this is a human-only decision."
      itemType="multi_l1_claims"
      verdicts={["pick_winner_a", "pick_winner_b", "both_valid_temporal_split", "escalate"]}
      renderBody={(payload) => (
        <MultiL1ReviewBody payload={payload as unknown as MultiL1ReviewPayload} />
      )}
    />
  );
}
