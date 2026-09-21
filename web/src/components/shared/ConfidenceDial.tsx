"use client";

/**
 * Circular confidence dial. SVG-based; the visx variant per spec is
 * substituted with plain SVG to avoid pulling in the d3 deps for a
 * single-arc widget.
 */

import { motion, useReducedMotion } from "framer-motion";

import { cn } from "@/lib/utils";

export interface ConfidenceDialProps {
  value: number; // 0–1
  size?: number;
  className?: string;
}

export function ConfidenceDial({ value, size = 56, className }: ConfidenceDialProps) {
  const reduced = useReducedMotion();
  const v = Math.max(0, Math.min(1, value));
  const radius = size / 2 - 4;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - v);
  const colorClass =
    v >= 0.9
      ? "text-success"
      : v >= 0.75
        ? "text-warning"
        : "text-destructive";

  return (
    <div
      className={cn("relative inline-flex items-center justify-center", className)}
      style={{ width: size, height: size }}
      role="meter"
      aria-valuemin={0}
      aria-valuemax={1}
      aria-valuenow={v}
      aria-label={`Confidence ${v.toFixed(2)}`}
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={3}
          className="stroke-surface-elevated"
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={3}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={reduced ? false : { strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: offset }}
          transition={{
            duration: reduced ? 0 : 0.6,
            ease: [0.16, 1, 0.3, 1] as const,
          }}
          className={cn("transition-colors", colorClass)}
        />
      </svg>
      <span
        className={cn(
          "absolute inset-0 flex items-center justify-center font-mono text-xs font-semibold tabular-nums",
          colorClass,
        )}
      >
        {v.toFixed(2)}
      </span>
    </div>
  );
}
