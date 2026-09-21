"use client";

import { AliasReviewBody, type AliasReviewPayload } from "@/components/hitl/AliasReviewBody";
import { ReviewPage } from "@/components/shared/ReviewPage";

export default function AliasReview() {
  return (
    <ReviewPage
      title="Alias review"
      description="Mention ↔ canonical entity matches in the 0.75–0.90 confidence band."
      itemType="alias_match"
      verdicts={["accept", "reject", "propose_alias", "defer"]}
      renderBody={(payload) => (
        <AliasReviewBody payload={payload as unknown as AliasReviewPayload} />
      )}
    />
  );
}
