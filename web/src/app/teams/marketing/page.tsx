"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, AlertCircle, Megaphone } from "lucide-react";
import Link from "next/link";

import { KpiCard } from "@/components/shared/KpiCard";
import { LoadingState } from "@/components/shared/LoadingState";
import { ErrorState } from "@/components/shared/ErrorState";
import { ConfidenceChip } from "@/components/shared/ConfidenceChip";
import { ContentGapMatrix } from "@/components/team/ContentGapMatrix";
import { TeamDashboardLayout } from "@/components/team/TeamDashboardLayout";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { teamsApi } from "@/lib/api/teams";

export default function MarketingDashboard() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["teams", "marketing"],
    queryFn: () => teamsApi.marketing(),
  });

  const gaps = data?.gaps ?? [];
  const totalVolume = gaps.reduce((a, g) => a + g.volume, 0);
  const topSeverity = gaps.length > 0 ? Math.max(...gaps.map((g) => g.gap_severity)) : 0;

  const matrixCells = gaps.flatMap((g) => {
    const bucket: "very_negative" | "negative" | "mixed" | "positive" =
      g.avg_sentiment <= -0.5
        ? "very_negative"
        : g.avg_sentiment <= 0
          ? "negative"
          : g.avg_sentiment <= 0.3
            ? "mixed"
            : "positive";
    return [{ topic: g.topic, bucket, volume: g.volume }];
  });

  return (
    <TeamDashboardLayout
      team="marketing"
      title="Marketing dashboard"
      description="Content gaps — high-volume topics without positive consensus. Ranked by gap severity."
      kpiStrip={
        !isLoading && !error ? (
          <div className="grid gap-3 sm:grid-cols-3">
            <KpiCard label="Content gaps" value={gaps.length} icon={Megaphone} accent="warning" />
            <KpiCard label="Mentions covered" value={totalVolume} accent="info" />
            <KpiCard
              label="Top severity"
              value={topSeverity.toFixed(2)}
              icon={AlertCircle}
              accent="destructive"
              hint="volume × |sentiment|"
            />
          </div>
        ) : null
      }
    >
      {isLoading && <LoadingState variant="card-list" rows={4} />}
      {error && (
        <ErrorState
          title="Couldn't load gaps"
          primaryAction={{ label: "Retry", onClick: () => refetch() }}
          technical={String(error)}
        />
      )}
      {data && matrixCells.length > 0 && (
        <ContentGapMatrix cells={matrixCells} />
      )}

      {data && (
        <ul className="space-y-2">
          {gaps.map((g, i) => (
            <li key={g.gap_id}>
              <Link
                href={`/teams/marketing/gap/${encodeURIComponent(g.gap_id)}`}
                className="group block focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                <Card className="transition-shadow group-hover:shadow-md">
                  <CardContent className="grid items-center gap-3 p-4 sm:grid-cols-[auto_1fr_auto_auto_auto_auto]">
                    <div className="font-mono text-xs text-muted-foreground tabular-nums">
                      #{i + 1}
                    </div>
                    <div className="min-w-0">
                      <h3 className="truncate text-sm font-semibold transition-colors group-hover:text-primary">
                        {g.topic}
                      </h3>
                      <p className="mt-0.5 text-[11px] text-muted-foreground">
                        {g.volume} mentions · {g.references.length} ref
                        {g.references.length === 1 ? "" : "s"}
                      </p>
                    </div>
                    <Badge variant="destructive" className="font-mono">
                      Sev {g.gap_severity.toFixed(2)}
                    </Badge>
                    <span className="hidden text-right sm:block">
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                        Sentiment
                      </p>
                      <span className="font-mono text-xs tabular-nums">
                        {g.avg_sentiment.toFixed(2)}
                      </span>
                    </span>
                    <ConfidenceChip value={Math.abs(g.avg_sentiment)} showLabel={false} />
                    <ArrowUpRight className="size-4 text-muted-foreground" />
                  </CardContent>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </TeamDashboardLayout>
  );
}
