/**
 * Inline confidence indicator. Color band per 01-design-system.md §1
 * confidence colors:
 *   ≥ 0.90  success (auto-accept)
 *   0.75–0.90 warning (HITL)
 *   < 0.75  destructive (reject)
 *   unknown muted
 */

import { cn } from "@/lib/utils";

export interface ConfidenceChipProps {
  value: number | null | undefined;
  showLabel?: boolean;
  className?: string;
}

export function ConfidenceChip({
  value,
  showLabel = true,
  className,
}: ConfidenceChipProps) {
  const band =
    value == null
      ? "muted"
      : value >= 0.9
        ? "success"
        : value >= 0.75
          ? "warning"
          : "destructive";

  const colorClass = {
    success: "text-success bg-success/10",
    warning: "text-warning bg-warning/10",
    destructive: "text-destructive bg-destructive/10",
    muted: "text-muted-foreground bg-muted/15",
  }[band];

  return (
    <span
      role="status"
      aria-label={value == null ? "Confidence: unknown" : `Confidence: ${value.toFixed(2)}`}
      className={cn(
        "inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-xs font-medium font-mono",
        colorClass,
        className,
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
      {showLabel && (value == null ? "—" : value.toFixed(2))}
    </span>
  );
}
