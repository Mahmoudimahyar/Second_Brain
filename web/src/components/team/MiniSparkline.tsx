"use client";

/**
 * MiniSparkline — small inline trend chart per
 * 07-component-vocabulary.md §6. Plain SVG path; Tremor's SparkArea
 * is the spec replacement when we wire Tremor in W4-stretch.
 */

import { useId } from "react";

import { cn } from "@/lib/utils";

export interface MiniSparklineProps {
  values: number[];
  width?: number;
  height?: number;
  className?: string;
  ariaLabel?: string;
}

export function MiniSparkline({
  values,
  width = 80,
  height = 20,
  className,
  ariaLabel = "Trend",
}: MiniSparklineProps) {
  const id = useId();
  if (values.length === 0) {
    return (
      <span className="text-[10px] text-muted-foreground">no data</span>
    );
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(1, max - min);
  const step = values.length > 1 ? width / (values.length - 1) : 0;
  const path = values
    .map((v, i) => {
      const x = i * step;
      const y = height - ((v - min) / span) * (height - 2) - 1;
      return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
  const area = `${path} L ${width} ${height} L 0 ${height} Z`;
  return (
    <svg
      width={width}
      height={height}
      role="img"
      aria-label={`${ariaLabel}: ${values.length} points, ${min.toFixed(2)} → ${max.toFixed(2)}`}
      className={cn("inline-block align-middle text-primary", className)}
    >
      <defs>
        <linearGradient id={`spark-${id}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.25" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#spark-${id})`} />
      <path d={path} fill="none" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}
