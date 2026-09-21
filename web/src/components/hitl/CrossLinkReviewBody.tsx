"use client";

/**
 * Per-type body for `cross_graph_link` HITL items per
 * 05-trust-tier-ux.md §12 + 06-hero-page-designs.md (cross-cutting).
 *
 * Side-by-side anchor ↔ candidate with similarity score + tier badges.
 */

import { ArrowLeftRight } from "lucide-react";

import { ConfidenceDial } from "@/components/shared/ConfidenceDial";
import { ProvenancePill } from "@/components/shared/ProvenancePill";
import { TierBadge, type SourceTier } from "@/components/shared/TierBadge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

export interface CrossLinkSide {
  node_id: string;
  display_name: string;
  tier: SourceTier;
  properties?: Record<string, string | number>;
}

export interface CrossLinkReviewPayload {
  anchor: CrossLinkSide;
  candidate: CrossLinkSide;
  similarity: number;
  band: "auto" | "hitl" | "reject";
  reasoning?: string[];
}

const BAND_META = {
  auto: { variant: "success" as const, label: "Auto-accept" },
  hitl: { variant: "warning" as const, label: "HITL" },
  reject: { variant: "destructive" as const, label: "Reject" },
};

export function CrossLinkReviewBody({ payload }: { payload: CrossLinkReviewPayload }) {
  return (
    <div className="space-y-3">
      <div className="grid items-center gap-3 sm:grid-cols-[1fr_auto_1fr]">
        <Side side={payload.anchor} label="Anchor (existing)" />
        <div className="flex flex-col items-center gap-1">
          <ConfidenceDial value={payload.similarity} size={56} />
          <Badge variant={BAND_META[payload.band].variant} className="font-mono text-[10px]">
            {BAND_META[payload.band].label}
          </Badge>
          <ArrowLeftRight className="size-4 text-muted-foreground" />
        </div>
        <Side side={payload.candidate} label="Candidate (new)" />
      </div>

      {payload.reasoning && payload.reasoning.length > 0 && (
        <Card>
          <CardContent className="p-3 text-xs">
            <p className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">
              Match reasoning
            </p>
            <ul className="list-disc space-y-0.5 pl-4 text-muted-foreground">
              {payload.reasoning.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <p className="text-[11px] text-muted-foreground">
        Accepting creates a <code className="font-mono">SAME_AS</code> edge.
        Both endpoints keep their own tier (
        <ProvenancePill tier={payload.anchor.tier} /> ↔{" "}
        <ProvenancePill tier={payload.candidate.tier} />).
      </p>
    </div>
  );
}

function Side({ side, label }: { side: CrossLinkSide; label: string }) {
  return (
    <Card>
      <CardContent className="space-y-2 p-3 text-sm">
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
          {label}
        </p>
        <div className="flex items-center gap-2">
          <TierBadge tier={side.tier} size="sm" detailed={false} />
          <span className="truncate font-semibold">{side.display_name}</span>
        </div>
        <p className="font-mono text-[11px] text-muted-foreground">
          {side.node_id}
        </p>
        {side.properties && (
          <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-[11px]">
            {Object.entries(side.properties).slice(0, 4).map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-muted-foreground">{k}</dt>
                <dd className="font-mono">{String(v)}</dd>
              </div>
            ))}
          </dl>
        )}
      </CardContent>
    </Card>
  );
}
