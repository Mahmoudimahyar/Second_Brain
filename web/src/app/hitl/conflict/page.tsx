"use client";

import {
  ConflictReviewBody,
  type ConflictReviewPayload,
} from "@/components/hitl/ConflictReviewBody";
import { ReviewPage } from "@/components/shared/ReviewPage";

export default function ConflictReview() {
  return (
    <ReviewPage
      title="Conflict review"
      description="Trust-tier clashes per FR-6.1. Confirm the system's resolution or override."
      itemType="conflict"
      verdicts={["accept_a", "accept_b", "temporal_split", "escalate"]}
      renderBody={(payload) => (
        <ConflictReviewBody payload={payload as unknown as ConflictReviewPayload} />
      )}
    />
  );
}
