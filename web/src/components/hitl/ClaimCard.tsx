"use client";

/**
 * ClaimCard — single-claim renderer used inside ConflictReviewBody,
 * MultiL1ReviewBody, etc. per 07-component-vocabulary.md §4 +
 * 05-trust-tier-ux.md §7.
 */

import { ExternalLink, Star } from "lucide-react";

import { ProvenancePill, type Rank } from "@/components/shared/ProvenancePill";
import { type SourceTier } from "@/components/shared/TierBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface Claim {
  claim_id?: string;
  value: string;
  tier: SourceTier;
  rank?: Rank;
  confidence?: number;
  source_label?: string;
  source_url?: string;
  references?: string[];
}

export interface ClaimCardProps {
  claim: Claim;
  emphasis?: "winner" | "loser" | "neutral";
  onOpenSource?: () => void;
}

const EMPHASIS_RING: Record<
  NonNullable<ClaimCardProps["emphasis"]>,
  string
> = {
  winner: "ring-2 ring-success/60",
  loser: "opacity-60 ring-1 ring-destructive/40",
  neutral: "",
};

export function ClaimCard({
  claim,
  emphasis = "neutral",
  onOpenSource,
}: ClaimCardProps) {
  return (
    <Card className={cn("relative", EMPHASIS_RING[emphasis])}>
      {emphasis === "winner" && (
        <Badge
          variant="success"
          className="absolute -top-2 left-3 inline-flex gap-1 font-mono text-[10px]"
        >
          <Star className="size-3" />
          Resolution winner
        </Badge>
      )}
      {emphasis === "loser" && (
        <Badge
          variant="destructive"
          className="absolute -top-2 left-3 font-mono text-[10px]"
        >
          Invalidated
        </Badge>
      )}
      <CardContent className="space-y-2 p-4">
        <p className="font-mono text-sm font-semibold">{claim.value}</p>
        <ProvenancePill
          tier={claim.tier}
          rank={claim.rank ?? "normal"}
          confidence={claim.confidence}
          referenceCount={claim.references?.length}
        />
        {claim.source_label && (
          <div className="flex items-center justify-between rounded-md border border-border/60 px-2 py-1 text-[11px] text-muted-foreground">
            <span className="truncate">{claim.source_label}</span>
            {claim.source_url && (
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                aria-label="Open source"
                onClick={onOpenSource}
                asChild={Boolean(!onOpenSource)}
              >
                {onOpenSource ? (
                  <ExternalLink className="size-3.5" />
                ) : (
                  <a href={claim.source_url} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="size-3.5" />
                  </a>
                )}
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
