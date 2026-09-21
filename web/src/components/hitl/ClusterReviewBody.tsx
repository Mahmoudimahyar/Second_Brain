"use client";

/**
 * Per-type body for `cluster_review` HITL items per
 * 06-hero-page-designs.md §3.
 */

import { Layers } from "lucide-react";

import { ConfidenceChip } from "@/components/shared/ConfidenceChip";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

export interface ClusterReviewPayload {
  cluster_id: string;
  label: string;
  description?: string;
  member_count: number;
  avg_sentiment?: number;
  sample_posts: { post_id: string; excerpt: string; score?: number }[];
}

export function ClusterReviewBody({ payload }: { payload: ClusterReviewPayload }) {
  return (
    <div className="space-y-3">
      <Card>
        <CardContent className="space-y-2 p-4">
          <div className="flex items-center gap-2">
            <Layers className="size-4 text-info" />
            <h3 className="text-sm font-semibold">{payload.label}</h3>
            <Badge variant="secondary" className="ml-auto font-mono text-[10px]">
              {payload.member_count} members
            </Badge>
            {payload.avg_sentiment != null && (
              <ConfidenceChip value={Math.abs(payload.avg_sentiment)} showLabel={false} />
            )}
          </div>
          {payload.description && (
            <p className="text-xs text-muted-foreground">{payload.description}</p>
          )}
          <p className="font-mono text-[10px] text-muted-foreground">
            {payload.cluster_id}
          </p>
        </CardContent>
      </Card>

      <div>
        <p className="mb-2 text-[10px] uppercase tracking-wider text-muted-foreground">
          Sample posts ({payload.sample_posts.length})
        </p>
        <ul className="space-y-1.5">
          {payload.sample_posts.map((p) => (
            <li
              key={p.post_id}
              className="flex items-start gap-3 rounded-md border border-border/60 px-3 py-2 text-sm"
            >
              <span className="mt-0.5 shrink-0 font-mono text-[10px] text-muted-foreground">
                {p.score ?? 0}
              </span>
              <div className="min-w-0 flex-1">
                <p className="line-clamp-2">{p.excerpt}</p>
                <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">
                  {p.post_id}
                </p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
