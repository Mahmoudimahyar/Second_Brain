"use client";

/**
 * Per-type body for `node_edge_proposal` HITL items per
 * 07-component-vocabulary.md §4.
 */

import { Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

export interface ProposalReviewPayload {
  proposal_id: string;
  proposal_type: "node" | "edge";
  proposed_label: string;
  proposed_schema?: Record<string, unknown>;
  rationale?: string;
  sample_extractions: { source_id: string; payload: Record<string, unknown> }[];
}

export function ProposalReviewBody({ payload }: { payload: ProposalReviewPayload }) {
  return (
    <div className="space-y-3">
      <Card>
        <CardContent className="space-y-2 p-4">
          <div className="flex items-center gap-2">
            <Sparkles className="size-4 text-accent" />
            <h3 className="text-sm font-semibold">
              {payload.proposal_type === "node" ? "Node type" : "Edge type"}:{" "}
              <span className="font-mono">{payload.proposed_label}</span>
            </h3>
            <Badge variant="secondary" className="ml-auto font-mono text-[10px]">
              {payload.proposal_type}
            </Badge>
          </div>
          {payload.rationale && (
            <p className="text-xs text-muted-foreground">{payload.rationale}</p>
          )}
          {payload.proposed_schema && (
            <details className="rounded-md border border-border/40 bg-surface/40 p-2">
              <summary className="cursor-pointer text-xs font-medium">
                Proposed schema
              </summary>
              <pre className="mt-1 max-h-40 overflow-auto font-mono text-[11px] text-muted-foreground">
                {JSON.stringify(payload.proposed_schema, null, 2)}
              </pre>
            </details>
          )}
        </CardContent>
      </Card>

      <div>
        <p className="mb-2 text-[10px] uppercase tracking-wider text-muted-foreground">
          Sample extractions ({payload.sample_extractions.length})
        </p>
        <ul className="space-y-1.5">
          {payload.sample_extractions.slice(0, 5).map((s, i) => (
            <li
              key={`${s.source_id}:${i}`}
              className="rounded-md border border-border/60 p-2 text-xs"
            >
              <p className="font-mono text-[10px] text-muted-foreground">
                {s.source_id}
              </p>
              <pre className="mt-1 max-h-24 overflow-auto font-mono text-[10px] text-muted-foreground">
                {JSON.stringify(s.payload, null, 2)}
              </pre>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
