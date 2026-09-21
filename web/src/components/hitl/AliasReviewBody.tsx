"use client";

/**
 * Per-type body for `alias_match` HITL items per
 * 07-component-vocabulary.md §4 + docs/08-ui/hitl-flows.md.
 *
 * Shows the mention + top-K canonical-entity candidates with
 * similarity scores, ranked descending. Top candidate is highlighted.
 */

import { ProvenancePill } from "@/components/shared/ProvenancePill";
import { TierBadge, type SourceTier } from "@/components/shared/TierBadge";
import { ConfidenceDial } from "@/components/shared/ConfidenceDial";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface AliasCandidate {
  canonical_id: string;
  canonical_name: string;
  similarity: number;
  tier: SourceTier;
}

export interface AliasReviewPayload {
  mention: string;
  source_post_id?: string;
  candidates: AliasCandidate[];
}

export function AliasReviewBody({ payload }: { payload: AliasReviewPayload }) {
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-border bg-background-warm/40 p-3 text-sm">
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
          Mention to resolve
        </p>
        <p className="mt-0.5 font-mono text-base font-semibold">
          {payload.mention}
        </p>
        {payload.source_post_id && (
          <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
            from {payload.source_post_id}
          </p>
        )}
      </div>
      <div>
        <p className="mb-2 text-[10px] uppercase tracking-wider text-muted-foreground">
          Top {payload.candidates.length} candidate
          {payload.candidates.length === 1 ? "" : "s"}
        </p>
        <ol className="space-y-2">
          {payload.candidates.map((c, i) => (
            <li key={c.canonical_id}>
              <Card className={cn(i === 0 && "ring-2 ring-primary/40")}>
                <CardContent className="flex items-center gap-3 p-3">
                  <ConfidenceDial value={c.similarity} size={44} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold">
                      {c.canonical_name}
                    </p>
                    <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                      {c.canonical_id}
                    </p>
                  </div>
                  <TierBadge tier={c.tier} size="sm" detailed={false} />
                </CardContent>
              </Card>
            </li>
          ))}
        </ol>
      </div>
      <ProvenancePillsLegend />
    </div>
  );
}

function ProvenancePillsLegend() {
  return (
    <p className="text-[10px] text-muted-foreground">
      Confidence color: <ProvenancePill tier="L1" rank="preferred" confidence={0.92} /> auto-accept ·{" "}
      <ProvenancePill tier="L2" rank="normal" confidence={0.82} /> HITL ·{" "}
      <ProvenancePill tier="L5" rank="normal" confidence={0.42} /> reject.
    </p>
  );
}
