"use client";

/**
 * MiniMap — top-right inset that previews the canvas viewport.
 * Per 07-component-vocabulary.md §5 + 03-graph-visualization.md.
 *
 * Renders a tiny scaled SVG of the same node set. Sigma sub-instance
 * is the spec's stretch implementation — the SVG version costs
 * fractions of a KB and stays in sync with the result set.
 */

import { useMemo } from "react";

import { type QueryResult } from "@/lib/api/client";
import { cn } from "@/lib/utils";

export interface MiniMapProps {
  results: QueryResult[];
  width?: number;
  height?: number;
  className?: string;
}

export function MiniMap({
  results,
  width = 160,
  height = 100,
  className,
}: MiniMapProps) {
  const positions = useMemo(() => {
    if (results.length === 0) return [] as { x: number; y: number; tier: string }[];
    // Hash-based pseudo-layout — deterministic, no force computation.
    return results.map((r, i) => {
      const a = (i * 0.6180339887) % 1;
      const b = ((i * 0.4142135624) + 0.137) % 1;
      return {
        x: a * (width - 4) + 2,
        y: b * (height - 4) + 2,
        tier: r.source_tier,
      };
    });
  }, [results, width, height]);

  if (results.length === 0) {
    return (
      <div
        aria-hidden="true"
        className={cn(
          "rounded border border-border bg-surface/40 p-2 text-[10px] text-muted-foreground",
          className,
        )}
        style={{ width, height }}
      >
        Mini-map empty
      </div>
    );
  }

  return (
    <svg
      width={width}
      height={height}
      role="img"
      aria-label={`Mini-map showing ${results.length} nodes`}
      className={cn(
        "rounded-md border border-border bg-surface/40 shadow-sm",
        className,
      )}
    >
      {positions.map((p, i) => (
        <circle
          key={i}
          cx={p.x}
          cy={p.y}
          r={1.5}
          className={`fill-tier-${p.tier.toLowerCase()}`}
        />
      ))}
    </svg>
  );
}
