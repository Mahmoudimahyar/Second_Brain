"use client";

import {
  ProposalReviewBody,
  type ProposalReviewPayload,
} from "@/components/hitl/ProposalReviewBody";
import { ReviewPage } from "@/components/shared/ReviewPage";

export default function ProposalReview() {
  return (
    <ReviewPage
      title="Node/edge proposal review"
      description="New type proposals from Pass 4 + the feedback loop. Approve to expand the schema; refine to give the next sweep guidance."
      itemType="node_edge_proposal"
      verdicts={["accept", "reject", "refine", "defer"]}
      renderBody={(payload) => (
        <ProposalReviewBody payload={payload as unknown as ProposalReviewPayload} />
      )}
    />
  );
}
