"use client";

import { use } from "react";
import { useQuery } from "@tanstack/react-query";

import { DashboardLayout } from "@/components/layouts/DashboardLayout";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState } from "@/components/shared/ErrorState";
import { KpiCard } from "@/components/shared/KpiCard";
import { LoadingState } from "@/components/shared/LoadingState";
import { SuggestedPostPanel, type SuggestedPost } from "@/components/team/SuggestedPostPanel";
import { TopicTrendChart } from "@/components/team/TopicTrendChart";
import { Hash, LineChart, TrendingUp } from "lucide-react";
import { teamsApi } from "@/lib/api/teams";

export default function SocialTopicDetail({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const topicId = decodeURIComponent(id);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["teams", "social", topicId],
    queryFn: () => teamsApi.socialTopic(topicId),
  });
  if (isLoading) return <LoadingState variant="dashboard" />;
  if (error)
    return (
      <ErrorState
        title="Couldn't load this topic"
        primaryAction={{ label: "Retry", onClick: () => refetch() }}
        technical={String(error)}
      />
    );
  if (!data) return null;
  const t = data.topic;
  // Per-day series comes from the backend's daily_buckets (V1.5d A3).
  const trendPoints = (t.daily_buckets ?? []).map((b) => ({
    date: b.date,
    volume: b.volume,
    sentiment: +b.avg_sentiment.toFixed(2),
  }));
  const posts: SuggestedPost[] = data.suggested_angles.map((a, i) => ({
    platform: (["twitter", "linkedin", "reddit"][i % 3] as SuggestedPost["platform"]),
    body: a.angle,
    rationale: a.rationale,
  }));
  return (
    <DashboardLayout
      title={t.name}
      description="Trending topic detail · sample drafts + per-day series"
      breadcrumbs={[
        { label: "Teams" },
        { label: "Social", href: "/teams/social" },
        { label: t.name },
      ]}
    >
      <div className="grid gap-3 sm:grid-cols-3">
        <KpiCard
          label="Trend ratio"
          value={`${t.trend_ratio.toFixed(2)}×`}
          icon={TrendingUp}
          accent={t.trend_ratio >= 2 ? "warning" : "info"}
        />
        <KpiCard
          label="Window volume"
          value={t.window_volume}
          icon={Hash}
        />
        <KpiCard
          label="Avg sentiment"
          value={t.avg_sentiment.toFixed(2)}
          accent={t.avg_sentiment < 0 ? "destructive" : "success"}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        {trendPoints.length > 0 ? (
          <TopicTrendChart
            data={trendPoints}
            title={`${trendPoints.length}-day trend`}
          />
        ) : (
          <EmptyState
            icon={<LineChart className="size-5" />}
            title="Per-day series unavailable"
            description="The underlying mentions don't carry timestamps yet. Re-run ingest with a timestamped source to populate the trend."
          />
        )}
        <SuggestedPostPanel posts={posts} />
      </div>
    </DashboardLayout>
  );
}
