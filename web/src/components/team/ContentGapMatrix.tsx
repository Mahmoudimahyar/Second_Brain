"use client";

/**
 * ContentGapMatrix — 2D heatmap of (topic × sentiment-band), colored
 * by volume. Per 07-component-vocabulary.md §6.
 *
 * Plain SVG grid; visx wrapper is the spec stretch — overkill for the
 * row counts marketing dashboards see today.
 */

import { scaleLinear } from "d3-scale";
import { useMemo } from "react";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export interface GapCell {
  topic: string;
  bucket: "very_negative" | "negative" | "mixed" | "positive";
  volume: number;
}

export interface ContentGapMatrixProps {
  cells: GapCell[];
  width?: number;
  height?: number;
}

const BUCKETS: GapCell["bucket"][] = [
  "very_negative",
  "negative",
  "mixed",
  "positive",
];
const BUCKET_LABEL: Record<GapCell["bucket"], string> = {
  very_negative: "≤ −0.5",
  negative: "−0.5 to 0",
  mixed: "0 to 0.3",
  positive: "≥ 0.3",
};

export function ContentGapMatrix({
  cells,
  width = 540,
  height = 220,
}: ContentGapMatrixProps) {
  const topics = useMemo(
    () => Array.from(new Set(cells.map((c) => c.topic))),
    [cells],
  );
  const cellW = (width - 110) / BUCKETS.length;
  const cellH = Math.max(20, (height - 40) / Math.max(1, topics.length));
  const volumeScale = useMemo(() => {
    const max = Math.max(1, ...cells.map((c) => c.volume));
    return scaleLinear<string>().domain([0, max]).range(["transparent", "hsl(var(--destructive))"]);
  }, [cells]);

  return (
    <TooltipProvider delayDuration={150}>
      <div className="rounded-md border border-border bg-surface/40 p-2">
        <svg
          width={width}
          height={height}
          role="img"
          aria-label="Content gap matrix — topics by sentiment bucket"
        >
          {/* column headers */}
          {BUCKETS.map((b, i) => (
            <text
              key={b}
              x={110 + i * cellW + cellW / 2}
              y={14}
              textAnchor="middle"
              className="fill-muted-foreground text-[10px] uppercase tracking-wider"
            >
              {BUCKET_LABEL[b]}
            </text>
          ))}
          {/* rows */}
          {topics.map((t, rowIdx) => (
            <g key={t} transform={`translate(0, ${24 + rowIdx * cellH})`}>
              <text
                x={4}
                y={cellH / 2 + 4}
                className="fill-foreground text-[11px] font-mono"
              >
                {t.slice(0, 18)}
              </text>
              {BUCKETS.map((b, colIdx) => {
                const cell = cells.find((c) => c.topic === t && c.bucket === b);
                const fill = cell ? volumeScale(cell.volume) : "transparent";
                return (
                  <Tooltip key={b}>
                    <TooltipTrigger asChild>
                      <rect
                        x={110 + colIdx * cellW + 2}
                        y={2}
                        width={cellW - 4}
                        height={cellH - 4}
                        rx={3}
                        fill={fill}
                        stroke="hsl(var(--border))"
                        strokeWidth={1}
                        className={cn(
                          "cursor-pointer transition-opacity hover:opacity-80",
                        )}
                      />
                    </TooltipTrigger>
                    <TooltipContent>
                      <div className="font-mono">{t}</div>
                      <div className="text-muted-foreground">
                        {BUCKET_LABEL[b]} · vol {cell?.volume ?? 0}
                      </div>
                    </TooltipContent>
                  </Tooltip>
                );
              })}
            </g>
          ))}
        </svg>
      </div>
    </TooltipProvider>
  );
}
