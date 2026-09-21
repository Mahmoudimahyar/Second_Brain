import { ReviewPage } from "@/components/shared/ReviewPage";

export default function EscalatedReview() {
  return (
    <ReviewPage
      title="Escalated items"
      itemType="escalated"
      verdicts={["resolve", "re_escalate", "defer"]}
    />
  );
}
