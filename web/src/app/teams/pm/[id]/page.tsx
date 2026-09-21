"use client";

import { use } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { DashboardLayout } from "@/components/layouts/DashboardLayout";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingState } from "@/components/shared/LoadingState";
import { PainPointDetailCard } from "@/components/team/PainPointDetailCard";
import { SuggestedAnglesPanel } from "@/components/team/SuggestedAnglesPanel";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { teamsApi } from "@/lib/api/teams";

export default function PMDetail({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const painPointId = decodeURIComponent(id);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["teams", "pm", painPointId],
    queryFn: () => teamsApi.pmDetail(painPointId),
  });
  if (isLoading) return <LoadingState variant="dashboard" />;
  if (error) {
    return (
      <ErrorState
        title="Couldn't load this pain point"
        primaryAction={{ label: "Retry", onClick: () => refetch() }}
        technical={String(error)}
      />
    );
  }
  if (!data) return null;
  const pp = data.pain_point;
  return (
    <DashboardLayout
      title={pp.title}
      description={`Pain point · ${pp.audience_segment}`}
      breadcrumbs={[
        { label: "Teams" },
        { label: "PM", href: "/teams/pm" },
        { label: pp.title },
      ]}
    >
      {/* tierMix / trend / topClusters now come from the backend (V1.5d
          A1 + A2). They render only when the data exists; empty maps /
          arrays mean the loader couldn't fill them and the card omits
          the corresponding section. */}
      <PainPointDetailCard
        title={pp.title}
        audience={pp.audience_segment}
        volume={pp.volume}
        avgSentiment={pp.avg_sentiment}
        tierMix={pp.tier_mix && Object.keys(pp.tier_mix).length > 0 ? pp.tier_mix : undefined}
        trend={(pp.daily_buckets ?? []).map((b) => b.volume)}
        topClusters={(data.top_clusters ?? []).map((c) => ({
          id: c.cluster_id,
          label: c.label,
          count: c.count,
        }))}
      />

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">References</CardTitle>
            <CardDescription>
              {pp.references.length} source row{pp.references.length === 1 ? "" : "s"}.
              Click any to drill down on the Level C graph view.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="grid gap-1.5 sm:grid-cols-2">
              {pp.references.map((ref) => (
                <li key={ref}>
                  <Button
                    asChild
                    variant="outline"
                    size="sm"
                    className="w-full justify-between font-mono text-xs"
                  >
                    <Link href={`/graph/analyzed?query=${encodeURIComponent(ref)}`}>
                      <span className="truncate">{ref}</span>
                    </Link>
                  </Button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <SuggestedAnglesPanel team="pm" angles={data.suggested_angles ?? []} />
      </div>
    </DashboardLayout>
  );
}
