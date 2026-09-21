"use client";

import {
  JudgeBreakdown,
  type JudgeBreakdownPayload,
} from "@/components/hitl/JudgeBreakdown";
import { ReviewPage } from "@/components/shared/ReviewPage";

export default function JudgeReview() {
  return (
    <ReviewPage
      title="Judge disagreement"
      description="Three-vendor LLM judges split. Per ADR-006 you pick the final verdict."
      itemType="judge_disagreement"
      verdicts={["pick_sonnet", "pick_gemini", "pick_gpt", "escalate"]}
      renderBody={(payload) => (
        <JudgeBreakdown payload={payload as unknown as JudgeBreakdownPayload} />
      )}
    />
  );
}
