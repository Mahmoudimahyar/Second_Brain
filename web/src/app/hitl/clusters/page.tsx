"use client";

import {
  ClusterReviewBody,
  type ClusterReviewPayload,
} from "@/components/hitl/ClusterReviewBody";
import { ReviewPage } from "@/components/shared/ReviewPage";

export default function ClusterReview() {
  return (
    <ReviewPage
      title="Cluster cull review"
      description="Approve, cull, merge or split the Pass-3 clusters before Pass 4 spends LLM dollars."
      itemType="cluster_review"
      verdicts={["keep", "cull", "merge_into", "split", "mark_anomaly", "defer"]}
      renderBody={(payload) => (
        <ClusterReviewBody payload={payload as unknown as ClusterReviewPayload} />
      )}
    />
  );
}
