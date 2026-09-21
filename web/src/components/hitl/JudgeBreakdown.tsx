"use client";

/**
 * Per-type body for `judge_disagreement` HITL items per ADR-006 +
 * 07-component-vocabulary.md §4.
 */

import { Gavel, MessageSquareWarning } from "lucide-react";

import { ConfidenceChip } from "@/components/shared/ConfidenceChip";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface JudgeVerdict {
  vendor: string;
  model: string;
  verdict: string;
  confidence?: number;
  reasoning?: string;
}

export interface JudgeBreakdownPayload {
  task: string;
  prompt_excerpt?: string;
  verdicts: JudgeVerdict[];
  majority?: string | null;
}

export function JudgeBreakdown({ payload }: { payload: JudgeBreakdownPayload }) {
  return (
    <div className="space-y-3">
      <div className="flex items-start gap-2 rounded-md border border-info/30 bg-info/5 p-3 text-sm">
        <MessageSquareWarning className="mt-0.5 size-4 shrink-0 text-info" />
        <div className="min-w-0">
          <p className="text-xs font-semibold">
            Three-vendor judges split on{" "}
            <span className="font-mono">{payload.task}</span>
          </p>
          {payload.majority ? (
            <p className="mt-1 text-xs text-muted-foreground">
              Majority leans towards{" "}
              <Badge variant="secondary" className="font-mono">
                {payload.majority}
              </Badge>{" "}
              — your tie-break is recorded as the final verdict.
            </p>
          ) : (
            <p className="mt-1 text-xs text-muted-foreground">
              No majority. Pick a verdict; your call writes the resolution.
            </p>
          )}
        </div>
      </div>

      {payload.prompt_excerpt && (
        <Card>
          <CardContent className="p-3 text-xs">
            <p className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">
              Prompt excerpt
            </p>
            <pre className="max-h-32 overflow-auto whitespace-pre-wrap font-mono text-[11px] text-muted-foreground">
              {payload.prompt_excerpt}
            </pre>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-2 sm:grid-cols-3">
        {payload.verdicts.map((v) => (
          <Card
            key={`${v.vendor}:${v.model}`}
            className={cn(
              "transition-shadow",
              payload.majority && v.verdict === payload.majority
                ? "ring-2 ring-success/40"
                : null,
            )}
          >
            <CardContent className="space-y-1.5 p-3 text-xs">
              <div className="flex items-center justify-between">
                <span className="inline-flex items-center gap-1 font-semibold">
                  <Gavel className="size-3.5 text-muted-foreground" />
                  {v.vendor}
                </span>
                {v.confidence != null && (
                  <ConfidenceChip value={v.confidence} showLabel={false} />
                )}
              </div>
              <p className="font-mono text-[10px] text-muted-foreground">{v.model}</p>
              <Badge
                variant={
                  payload.majority && v.verdict === payload.majority
                    ? "success"
                    : "secondary"
                }
                className="font-mono"
              >
                {v.verdict}
              </Badge>
              {v.reasoning && (
                <p className="line-clamp-3 text-[11px] text-muted-foreground">
                  {v.reasoning}
                </p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
