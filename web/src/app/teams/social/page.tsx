"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { ArrowUpRight, Hash, LineChart, TrendingUp } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/shared/EmptyState";
import { KpiCard } from "@/components/shared/KpiCard";
import { LoadingState } from "@/components/shared/LoadingState";
import { ErrorState } from "@/components/shared/ErrorState";
import { ConfidenceChip } from "@/components/shared/ConfidenceChip";
import { MiniSparkline } from "@/components/team/MiniSparkline";
import { TeamDashboardLayout } from "@/components/team/TeamDashboardLayout";
import { TopicTrendChart } from "@/components/team/TopicTrendChart";
import { TrendingTopicCarousel } from "@/components/team/TrendingTopicCarousel";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { teamsApi } from "@/lib/api/teams";

export default function SocialDashboard() {
  const router = useRouter();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["teams", "social"],
    queryFn: () => teamsApi.social(),
  });

  const trends = data?.trends ?? [];
  const totalMentions = trends.reduce((acc, t) => acc + t.window_volume, 0);
  const topRatio = trends.length > 0 ? Math.max(...trends.map((t) => t.trend_ratio)) : 0;
  // Per-topic carousel cards pull their trend straight from the
  // backend's `daily_buckets` (volume per day inside the trending
  // window). Topics with no bucket data render without a sparkline —
  // honest absence, not synthesis.
  const carouselTopics = trends.slice(0, 8).map((t) => ({
    topic_id: t.topic_id,
    name: t.name,
    trend_ratio: t.trend_ratio,
    window_volume: t.window_volume,
    trend: (t.daily_buckets ?? []).map((b) => b.volume),
  }));
  // Aggregate right-rail series: sum volume per date across all topics,
  // average sentiment weighted by volume. Honest aggregation of the
  // per-topic series the backend already ships.
  const aggregateByDate = new Map<
    string,
    { volume: number; sentSum: number }
  >();
  for (const t of trends) {
    for (const b of t.daily_buckets ?? []) {
      const cur = aggregateByDate.get(b.date) ?? { volume: 0, sentSum: 0 };
      cur.volume += b.volume;
      cur.sentSum += b.avg_sentiment * b.volume;
      aggregateByDate.set(b.date, cur);
    }
  }
  const aggregateSeries = Array.from(aggregateByDate.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, v]) => ({
      date,
      volume: v.volume,
      sentiment: v.volume > 0 ? +(v.sentSum / v.volume).toFixed(2) : 0,
    }));

  return (
    <TeamDashboardLayout
      team="social"
      title="Social dashboard"
      description="Trending topics in the last 30 days, ranked by trend ratio."
      kpiStrip={
        !isLoading && !error ? (
          <div className="grid gap-3 sm:grid-cols-3">
            <KpiCard label="Trending topics" value={trends.length} icon={TrendingUp} />
            <KpiCard label="Mentions (window)" value={totalMentions} icon={Hash} accent="info" />
            <KpiCard
              label="Top trend ratio"
              value={`${topRatio.toFixed(2)}×`}
              accent="accent"
              hint="vs baseline"
            />
          </div>
        ) : null
      }
    >
      {isLoading && <LoadingState variant="card-list" rows={4} />}
      {error && (
        <ErrorState
          title="Couldn't load trends"
          primaryAction={{ label: "Retry", onClick: () => refetch() }}
          technical={String(error)}
        />
      )}
      {data && (
        <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
          <div className="space-y-4">
            <TrendingTopicCarousel
              topics={carouselTopics}
              onPick={(id) =>
                router.push(`/teams/social/topic/${encodeURIComponent(id)}`)
              }
            />
            <ul className="space-y-2">
              {trends.map((t, i) => (
            <li key={t.topic_id}>
              <Link
                href={`/teams/social/topic/${encodeURIComponent(t.topic_id)}`}
                className="group block focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                <Card className="transition-shadow group-hover:shadow-md">
                  <CardContent className="grid items-center gap-3 p-4 sm:grid-cols-[auto_1fr_auto_auto_auto_auto]">
                    <div className="font-mono text-xs text-muted-foreground tabular-nums">
                      #{i + 1}
                    </div>
                    <div className="min-w-0">
                      <h3 className="truncate text-sm font-semibold transition-colors group-hover:text-primary">
                        {t.name}
                      </h3>
                      <p className="mt-0.5 text-[11px] text-muted-foreground">
                        {t.window_volume} mentions
                      </p>
                    </div>
                    <Badge
                      variant={t.trend_ratio >= 2 ? "warning" : "secondary"}
                      className="font-mono"
                    >
                      {t.trend_ratio.toFixed(2)}×
                    </Badge>
                    <ConfidenceChip value={Math.abs(t.avg_sentiment)} showLabel={false} />
                    {(t.daily_buckets ?? []).length > 0 ? (
                      <MiniSparkline
                        values={(t.daily_buckets ?? []).map((b) => b.volume)}
                        width={64}
                        height={20}
                      />
                    ) : (
                      <Badge variant="outline" className="font-mono text-[10px]">
                        no trend
                      </Badge>
                    )}
                    <ArrowUpRight className="size-4 text-muted-foreground" />
                  </CardContent>
                </Card>
              </Link>
            </li>
          ))}
            </ul>
          </div>
          <aside className="space-y-4">
            {aggregateSeries.length > 0 ? (
              <TopicTrendChart
                title="Volume + sentiment (aggregate)"
                data={aggregateSeries}
              />
            ) : (
              <EmptyState
                icon={<LineChart className="size-5" />}
                title="Volume + sentiment trend"
                description="No per-day data in this window. Pull a source or re-run Pass-4 to populate the trending series."
              />
            )}
          </aside>
        </div>
      )}
    </TeamDashboardLayout>
  );
}
