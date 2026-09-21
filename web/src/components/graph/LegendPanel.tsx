"use client";

/**
 * LegendPanel — collapsible legend per 03-graph-visualization.md +
 * 07-component-vocabulary.md §5. Explains tier colors + edge styling
 * + status overlays. Always available; collapsible.
 */

import { ChevronDown } from "lucide-react";
import { useState } from "react";

import { TierBadge, type SourceTier } from "@/components/shared/TierBadge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const TIERS: SourceTier[] = ["L1", "L2", "L3", "L4", "L5"];

const EDGE_STYLES: { label: string; sample: string }[] = [
  { label: "Preferred rank", sample: "stroke-foreground stroke-[2.5]" },
  { label: "Normal", sample: "stroke-muted-foreground stroke-[1.5]" },
  { label: "Deprecated", sample: "stroke-muted-foreground stroke-1 [stroke-dasharray:3_3] opacity-40" },
];

export function LegendPanel() {
  const [open, setOpen] = useState(true);
  return (
    <Card>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:bg-surface/60"
      >
        Legend
        <ChevronDown
          className={cn(
            "size-3.5 transition-transform",
            open && "rotate-180",
          )}
        />
      </button>
      {open && (
        <CardContent className="space-y-3 pt-0 text-xs">
          <div>
            <p className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">
              Source tier
            </p>
            <ul className="flex flex-wrap gap-1.5">
              {TIERS.map((t) => (
                <li key={t}>
                  <TierBadge tier={t} size="sm" detailed={false} />
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">
              Edge rank
            </p>
            <ul className="space-y-1">
              {EDGE_STYLES.map((e) => (
                <li key={e.label} className="flex items-center gap-2">
                  <svg
                    width={32}
                    height={6}
                    aria-hidden="true"
                    className="text-current"
                  >
                    <line
                      x1="0"
                      y1="3"
                      x2="32"
                      y2="3"
                      className={e.sample}
                    />
                  </svg>
                  <span>{e.label}</span>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">
              Status overlays
            </p>
            <ul className="space-y-1 text-muted-foreground">
              <li>
                <span className="text-destructive line-through">
                  invalidated_by_official_data
                </span>{" "}
                — red strike
              </li>
              <li>
                <span className="rounded-full ring-2 ring-warning/50 px-1.5">
                  anomaly
                </span>{" "}
                — orange ring
              </li>
              <li>
                <span className="hitl-pending rounded-full px-1.5">pending</span>{" "}
                — yellow pulse
              </li>
            </ul>
          </div>
        </CardContent>
      )}
    </Card>
  );
}
