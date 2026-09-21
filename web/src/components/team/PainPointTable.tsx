"use client";

/**
 * PainPointTable — per 06-hero-page-designs.md §6 + 07-component-
 * vocabulary.md §6. Custom table (TanStack Table virtual scroll is the
 * spec but the row count for V1.5 is small enough that the simple
 * grid suffices).
 */

import { ArrowUpRight, MessageSquare } from "lucide-react";
import Link from "next/link";

import { ConfidenceChip } from "@/components/shared/ConfidenceChip";
import { EmptyState } from "@/components/shared/EmptyState";
import { MiniSparkline } from "@/components/team/MiniSparkline";
import { TierMixBar, type TierComposition } from "@/components/team/TierMixBar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export interface PainPoint {
  pain_point_id: string;
  title: string;
  audience_segment: string;
  volume: number;
  avg_sentiment: number;
  references: string[];
  /** Optional decorative fields. Pass only when the backend genuinely
   * returns them — never synthesize. The row degrades gracefully when
   * absent (no trend → "no trend" badge; no tier_mix → row omitted). */
  tier_mix?: TierComposition;
  trend?: number[];
}

export interface PainPointTableProps {
  painPoints: PainPoint[];
}

export function PainPointTable({ painPoints }: PainPointTableProps) {
  if (painPoints.length === 0) {
    return (
      <EmptyState
        icon={<MessageSquare className="size-5" />}
        title="No pain points yet"
        description="Run Pass-4 sentiment extraction on the corpus, or connect a forum source."
        primaryAction={{ label: "Connect a source", href: "/ingest/new" }}
      />
    );
  }

  return (
    <ul className="space-y-2">
      {painPoints.map((pp, i) => (
        <li key={pp.pain_point_id}>
          <Card className="transition-shadow hover:shadow-md">
            <CardContent className="grid items-center gap-4 p-4 sm:grid-cols-[auto_1fr_auto_auto_auto_auto]">
              <div className="font-mono text-xs text-muted-foreground tabular-nums">
                #{i + 1}
              </div>

              <Link
                href={`/teams/pm/${encodeURIComponent(pp.pain_point_id)}`}
                className="group min-w-0"
              >
                <h3 className="truncate text-sm font-semibold transition-colors group-hover:text-primary">
                  {pp.title}
                </h3>
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  {pp.audience_segment} · {pp.references.length} ref
                  {pp.references.length === 1 ? "" : "s"}
                </p>
              </Link>

              <div className="hidden text-right sm:block">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  Volume
                </p>
                <p className="font-mono text-sm tabular-nums">{pp.volume}</p>
              </div>

              <div className="hidden text-right sm:block">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  Sentiment
                </p>
                <ConfidenceChip value={Math.abs(pp.avg_sentiment)} showLabel={false} />
                <span className="ml-1 font-mono text-xs tabular-nums">
                  {pp.avg_sentiment.toFixed(2)}
                </span>
              </div>

              {pp.trend && pp.trend.length > 0 ? (
                <MiniSparkline values={pp.trend} width={64} height={20} />
              ) : (
                <Badge variant="outline" className="font-mono text-[10px]">
                  no trend
                </Badge>
              )}

              <Button asChild variant="ghost" size="icon" aria-label="Open detail">
                <Link href={`/teams/pm/${encodeURIComponent(pp.pain_point_id)}`}>
                  <ArrowUpRight className="size-4" />
                </Link>
              </Button>

              {pp.tier_mix && (
                <div className="col-span-full mt-1">
                  <TierMixBar composition={pp.tier_mix} label={`Tier mix · ${pp.title}`} />
                </div>
              )}
            </CardContent>
          </Card>
        </li>
      ))}
    </ul>
  );
}
