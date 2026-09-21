"use client";

/**
 * GapDetailPanel — single-gap drill-down for `/teams/marketing/gap/[id]`
 * per 07-component-vocabulary.md §6.
 */

import { AlertCircle } from "lucide-react";

import { ConfidenceChip } from "@/components/shared/ConfidenceChip";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export interface GapDetailPanelProps {
  topic: string;
  volume: number;
  avgSentiment: number;
  severity: number;
  references: string[];
  excerpts?: string[];
}

export function GapDetailPanel({
  topic,
  volume,
  avgSentiment,
  severity,
  references,
  excerpts = [],
}: GapDetailPanelProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <AlertCircle className="size-4 text-destructive" />
          {topic}
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          {volume} mentions ·{" "}
          <Badge variant="destructive" className="ml-1 font-mono">
            Severity {severity.toFixed(2)}
          </Badge>{" "}
          · sentiment{" "}
          <ConfidenceChip value={Math.abs(avgSentiment)} showLabel={false} />{" "}
          <span className="font-mono">{avgSentiment.toFixed(2)}</span>
        </p>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {excerpts.length > 0 && (
          <div>
            <p className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">
              Representative excerpts
            </p>
            <ul className="space-y-1">
              {excerpts.slice(0, 3).map((ex, i) => (
                <li
                  key={`${ex.slice(0, 16)}:${i}`}
                  className="rounded-md border border-border/60 bg-surface/40 p-2 text-xs"
                >
                  {ex}
                </li>
              ))}
            </ul>
          </div>
        )}
        {references.length > 0 && (
          <div>
            <p className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">
              References ({references.length})
            </p>
            <ul className="flex flex-wrap gap-1">
              {references.slice(0, 12).map((r) => (
                <li key={r}>
                  <Badge variant="outline" className="font-mono text-[10px]">
                    {r}
                  </Badge>
                </li>
              ))}
              {references.length > 12 && (
                <li className="text-[10px] text-muted-foreground">
                  + {references.length - 12} more
                </li>
              )}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
