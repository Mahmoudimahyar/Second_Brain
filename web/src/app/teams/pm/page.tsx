"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { MessageSquare, Star, Users } from "lucide-react";

import { KpiCard } from "@/components/shared/KpiCard";
import { LoadingState } from "@/components/shared/LoadingState";
import { ErrorState } from "@/components/shared/ErrorState";
import { PainPointTable, type PainPoint } from "@/components/team/PainPointTable";
import { TeamDashboardLayout } from "@/components/team/TeamDashboardLayout";
import { teamsApi } from "@/lib/api/teams";

// `trend` + `tier_mix` come straight from the backend now (V1.5d A1):
// `daily_buckets` → trend, `tier_mix` → tier_mix. Both degrade to empty
// when the underlying input rows didn't carry timestamps / tier info.

export default function PMDashboard() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["teams", "pm"],
    queryFn: () => teamsApi.pm(),
  });

  const painPoints = useMemo<PainPoint[]>(() => {
    if (!data) return [];
    return data.pain_points.map((p) => ({
      ...p,
      // Extract per-day volume counts for the sparkline (the backend
      // ships the full TrendBucket; UI just needs the volume series).
      trend: (p.daily_buckets ?? []).map((b) => b.volume),
      // Pass through tier_mix as-is — TierMixBar consumes Record<tier,fraction>.
      tier_mix: p.tier_mix,
    }));
  }, [data]);

  const total = painPoints.reduce((acc, pp) => acc + pp.volume, 0);
  const avgSent =
    painPoints.length > 0
      ? painPoints.reduce((acc, pp) => acc + pp.avg_sentiment, 0) /
        painPoints.length
      : 0;

  return (
    <TeamDashboardLayout
      team="pm"
      title="PM dashboard"
      description="Ranked pain points from forum + connector data. Click any row for suggested angles + drill-down."
      kpiStrip={
        !isLoading && !error ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <KpiCard
              label="Pain points"
              value={painPoints.length}
              icon={MessageSquare}
              accent="primary"
            />
            <KpiCard
              label="Total mentions"
              value={total}
              icon={Users}
              accent="info"
            />
            <KpiCard
              label="Avg sentiment"
              value={avgSent.toFixed(2)}
              accent={avgSent < -0.3 ? "destructive" : "warning"}
              hint={
                avgSent < -0.3
                  ? "Strongly negative"
                  : avgSent < 0
                    ? "Net negative"
                    : "Mixed / positive"
              }
            />
            <KpiCard
              label="L1 anchors covered"
              value={Math.min(painPoints.length, 4)}
              icon={Star}
              accent="accent"
              hint="ADEA SDE2 / SDE3 / SDE4"
            />
          </div>
        ) : null
      }
    >
      {isLoading && <LoadingState variant="table" rows={6} cols={5} />}
      {error && (
        <ErrorState
          title="Couldn't load the PM dashboard"
          primaryAction={{ label: "Retry", onClick: () => refetch() }}
          technical={String(error)}
        />
      )}
      {data && <PainPointTable painPoints={painPoints} />}
    </TeamDashboardLayout>
  );
}
