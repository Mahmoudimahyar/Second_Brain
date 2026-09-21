"use client";

/**
 * TierMixBar — stacked horizontal bar showing tier composition of an
 * insight. Per docs/08-ui/v1.5-redesign/05-trust-tier-ux.md §9.
 */

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { type SourceTier } from "@/components/shared/TierBadge";

export type TierComposition = Partial<Record<SourceTier, number>>;

export interface TierMixBarProps {
  composition: TierComposition;
  width?: number;
  label?: string;
}

const TIER_BG: Record<SourceTier, string> = {
  L1: "bg-tier-l1",
  L2: "bg-tier-l2",
  L3: "bg-tier-l3",
  L4: "bg-tier-l4",
  L5: "bg-tier-l5",
};

export function TierMixBar({ composition, width, label = "Tier mix" }: TierMixBarProps) {
  const total = (Object.values(composition) as number[]).reduce(
    (a, b) => a + (b || 0),
    0,
  );
  const tiers = (Object.keys(composition) as SourceTier[]).filter(
    (t) => (composition[t] || 0) > 0,
  );
  const safeTotal = total > 0 ? total : 1;
  return (
    <TooltipProvider delayDuration={150}>
      <div className="space-y-1" style={width ? { width } : undefined}>
        <div
          role="img"
          aria-label={`${label}: ${tiers
            .map((t) => `${t} ${Math.round(((composition[t] || 0) / safeTotal) * 100)}%`)
            .join(", ")}`}
          className="flex h-2 w-full overflow-hidden rounded-full bg-surface"
        >
          {tiers.map((tier) => {
            const pct = ((composition[tier] || 0) / safeTotal) * 100;
            return (
              <Tooltip key={tier}>
                <TooltipTrigger asChild>
                  <span
                    className={`block h-full transition-all motion-safe:hover:opacity-80 ${TIER_BG[tier]}`}
                    style={{ width: `${pct}%` }}
                  />
                </TooltipTrigger>
                <TooltipContent>
                  <div className="font-mono">{tier}</div>
                  <div className="text-muted-foreground">
                    {Math.round(pct)}%
                  </div>
                </TooltipContent>
              </Tooltip>
            );
          })}
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-muted-foreground">
          {tiers.map((t) => {
            const pct = Math.round(((composition[t] || 0) / safeTotal) * 100);
            return (
              <span key={t} className="font-mono">
                {t} {pct}%
              </span>
            );
          })}
        </div>
      </div>
    </TooltipProvider>
  );
}
