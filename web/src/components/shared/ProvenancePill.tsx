/**
 * ProvenancePill — per docs/08-ui/v1.5-redesign/05-trust-tier-ux.md §2.
 *
 * Inline {TierBadge + rank chip + confidence dot + ref count}. Always
 * appears next to any rendered claim / node / edge with a `references`
 * array (V1 NFR-4 citation traceability invariant).
 */

import { ExternalLink } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ConfidenceChip } from "./ConfidenceChip";
import { TierBadge, type SourceTier } from "./TierBadge";
import { cn } from "@/lib/utils";

export type Rank = "preferred" | "normal" | "deprecated";

export interface ProvenancePillProps {
  tier: SourceTier;
  rank?: Rank;
  confidence?: number | null;
  referenceCount?: number;
  onClickReferences?: () => void;
  className?: string;
}

const RANK_STYLE: Record<Rank, string> = {
  preferred: "font-semibold text-foreground",
  normal: "text-muted-foreground",
  deprecated: "text-muted-foreground line-through opacity-60",
};

export function ProvenancePill({
  tier,
  rank = "normal",
  confidence = null,
  referenceCount,
  onClickReferences,
  className,
}: ProvenancePillProps) {
  return (
    <span
      className={cn(
        "inline-flex flex-wrap items-center gap-1.5 align-middle",
        className,
      )}
    >
      <TierBadge tier={tier} size="sm" />
      <span
        className={cn("text-[11px] uppercase tracking-wider", RANK_STYLE[rank])}
      >
        {rank}
      </span>
      {confidence != null && <ConfidenceChip value={confidence} />}
      {typeof referenceCount === "number" && referenceCount > 0 && (
        <Button
          variant="ghost"
          size="sm"
          className="h-6 gap-1 px-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground"
          onClick={onClickReferences}
          aria-label={`Show ${referenceCount} reference${referenceCount === 1 ? "" : "s"}`}
        >
          {referenceCount} ref{referenceCount === 1 ? "" : "s"}
          <ExternalLink className="size-3" />
        </Button>
      )}
    </span>
  );
}
