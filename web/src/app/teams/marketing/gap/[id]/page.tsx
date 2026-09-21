"use client";

import { use } from "react";
import { useQuery } from "@tanstack/react-query";

import { DashboardLayout } from "@/components/layouts/DashboardLayout";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingState } from "@/components/shared/LoadingState";
import { GapDetailPanel } from "@/components/team/GapDetailPanel";
import { SuggestedAnglesPanel } from "@/components/team/SuggestedAnglesPanel";
import { teamsApi } from "@/lib/api/teams";

export default function MarketingGapDetail({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const gapId = decodeURIComponent(id);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["teams", "marketing", gapId],
    queryFn: () => teamsApi.marketingGap(gapId),
  });
  if (isLoading) return <LoadingState variant="dashboard" />;
  if (error)
    return (
      <ErrorState
        title="Couldn't load this gap"
        primaryAction={{ label: "Retry", onClick: () => refetch() }}
        technical={String(error)}
      />
    );
  if (!data) return null;
  return (
    <DashboardLayout
      title={data.gap.topic}
      description={`Content gap · severity ${data.gap.gap_severity.toFixed(2)}`}
      breadcrumbs={[
        { label: "Teams" },
        { label: "Marketing", href: "/teams/marketing" },
        { label: data.gap.topic },
      ]}
    >
      <GapDetailPanel
        topic={data.gap.topic}
        volume={data.gap.volume}
        avgSentiment={data.gap.avg_sentiment}
        severity={data.gap.gap_severity}
        references={data.gap.references}
        excerpts={data.gap.sample_excerpts}
      />
      <div className="mt-6">
        <SuggestedAnglesPanel team="marketing" angles={data.suggested_angles ?? []} />
      </div>
    </DashboardLayout>
  );
}
