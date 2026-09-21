"use client";

/**
 * PainPointDetailCard — header card used on `/teams/pm/[id]` per
 * 06-hero-page-designs.md §6.
 */

import { MessageSquare, TrendingDown, TrendingUp, Users } from "lucide-react";

import { KpiCard } from "@/components/shared/KpiCard";
import { TierMixBar, type TierComposition } from "@/components/team/TierMixBar";
import { MiniSparkline } from "@/components/team/MiniSparkline";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export interface PainPointDetailCardProps {
  title: string;
  audience: string;
  volume: number;
  avgSentiment: number;
  tierMix?: TierComposition;
  trend?: number[];
  topClusters?: { id: string; label: string; count: number }[];
}

export function PainPointDetailCard({
  title,
  audience,
  volume,
  avgSentiment,
  tierMix,
  trend,
  topClusters = [],
}: PainPointDetailCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        <p className="text-xs text-muted-foreground">
          Segment <span className="font-mono">{audience}</span>
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <KpiCard label="Mentions" value={volume} icon={Users} accent="info" />
          <KpiCard
            label="Sentiment"
            value={avgSentiment.toFixed(2)}
            icon={avgSentiment < 0 ? TrendingDown : TrendingUp}
            accent={avgSentiment < -0.3 ? "destructive" : "warning"}
          />
          <KpiCard
            label="Top clusters"
            value={topClusters.length}
            icon={MessageSquare}
            accent="primary"
          />
        </div>
        {tierMix && (
          <div className="space-y-1">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Tier mix
            </p>
            <TierMixBar composition={tierMix} label={`Tier mix · ${title}`} />
          </div>
        )}
        {trend && trend.length > 0 && (
          <div className="space-y-1">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Trend (last {trend.length} buckets)
            </p>
            <MiniSparkline values={trend} width={280} height={36} />
          </div>
        )}
        {topClusters.length > 0 && (
          <div className="space-y-1">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Top contributing clusters
            </p>
            <ul className="space-y-1 text-sm">
              {topClusters.map((c) => (
                <li
                  key={c.id}
                  className="flex items-center justify-between rounded-md border border-border/60 px-3 py-1.5"
                >
                  <span>{c.label}</span>
                  <span className="font-mono text-xs text-muted-foreground">
                    {c.count} posts
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
