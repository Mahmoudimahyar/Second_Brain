"use client";

/**
 * TrustMeter — per docs/08-ui/v1.5-redesign/05-trust-tier-ux.md §3.
 *
 * Composes (tier × rank × halo decay × credibility) → ranking_score.
 * Visx is in the V1.5d library list but not installed yet; using
 * plain SVG bars per spec — visual identical, smaller bundle.
 */

import { motion, useReducedMotion } from "framer-motion";

import type { Rank } from "@/components/shared/ProvenancePill";
import type { SourceTier } from "@/components/shared/TierBadge";
import { cn } from "@/lib/utils";

const TIER_SCORE: Record<SourceTier, number> = {
  L1: 1.0,
  L2: 0.85,
  L3: 0.7,
  L4: 0.55,
  L5: 0.4,
};

const RANK_SCORE: Record<Rank, number> = {
  preferred: 1.0,
  normal: 0.85,
  deprecated: 0.4,
};

export interface TrustMeterProps {
  tier: SourceTier;
  rank: Rank;
  haloDecay?: number; // 0–1
  credibility?: number; // 0–1
  className?: string;
}

interface Component {
  label: string;
  value: number;
  display: string;
}

function Bar({ value, color }: { value: number; color: string }) {
  const reduced = useReducedMotion();
  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(value * 100)}
      aria-valuemin={0}
      aria-valuemax={100}
      className="h-1.5 w-full overflow-hidden rounded-full bg-surface"
    >
      <motion.div
        initial={reduced ? false : { width: 0 }}
        animate={{ width: `${value * 100}%` }}
        transition={{
          duration: reduced ? 0 : 0.4,
          ease: [0.16, 1, 0.3, 1] as const,
        }}
        className={cn("h-full rounded-full", color)}
      />
    </div>
  );
}

export function TrustMeter({
  tier,
  rank,
  haloDecay = 1,
  credibility = 1,
  className,
}: TrustMeterProps) {
  const components: Component[] = [
    {
      label: `Tier ${tier}`,
      value: TIER_SCORE[tier],
      display: TIER_SCORE[tier].toFixed(2),
    },
    { label: `Rank ${rank}`, value: RANK_SCORE[rank], display: RANK_SCORE[rank].toFixed(2) },
    { label: "HALO decay", value: haloDecay, display: haloDecay.toFixed(2) },
    { label: "Credibility", value: credibility, display: credibility.toFixed(2) },
  ];
  const score = components.reduce((acc, c) => acc * c.value, 1);
  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-muted-foreground">Trust score</span>
        <span className="font-mono text-base font-semibold tabular-nums">
          {score.toFixed(2)}
        </span>
      </div>
      <dl className="space-y-1.5">
        {components.map((c, i) => (
          <div key={c.label} className="grid grid-cols-[auto_1fr_auto] items-center gap-2">
            <dt className="text-[11px] text-muted-foreground">{c.label}</dt>
            <dd className="contents">
              <div className="contents">
                <Bar
                  value={c.value}
                  color={
                    i === 0
                      ? "bg-accent"
                      : i === 1
                        ? "bg-primary"
                        : "bg-info"
                  }
                />
                <span className="font-mono text-[11px] text-muted-foreground tabular-nums">
                  {c.display}
                </span>
              </div>
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
