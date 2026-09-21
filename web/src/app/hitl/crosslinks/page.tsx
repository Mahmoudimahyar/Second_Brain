"use client";

import {
  CrossLinkReviewBody,
  type CrossLinkReviewPayload,
} from "@/components/hitl/CrossLinkReviewBody";
import { ReviewPage } from "@/components/shared/ReviewPage";

export default function CrossLinksReview() {
  return (
    <ReviewPage
      title="Cross-graph link review"
      description="Anchor ↔ candidate matches in the 0.75–0.90 confidence band. Accept to write a SAME_AS edge."
      itemType="cross_graph_link"
      verdicts={["accept", "reject", "propose_alias", "defer", "escalate"]}
      renderBody={(payload) => (
        <CrossLinkReviewBody payload={payload as unknown as CrossLinkReviewPayload} />
      )}
    />
  );
}
