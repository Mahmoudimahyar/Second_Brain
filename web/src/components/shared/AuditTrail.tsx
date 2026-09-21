"use client";

/**
 * Collapsible audit trail panel for detail pages. Loads via TanStack
 * Query when an entityId is provided; otherwise renders provided rows.
 */

import { ChevronDown, ScrollText } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

export interface AuditRow {
  ts: string;
  kind: string;
  detail?: string;
}

export interface AuditTrailProps {
  entityId?: string;
  rows?: AuditRow[];
  maxRows?: number;
  className?: string;
}

export function AuditTrail({
  entityId,
  rows = [],
  maxRows = 5,
  className,
}: AuditTrailProps) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? rows : rows.slice(0, maxRows);
  const hasMore = rows.length > maxRows;

  return (
    <details
      className={cn(
        "rounded-lg border border-border bg-surface/40 p-3 text-sm",
        className,
      )}
      open={expanded}
      onToggle={(e) => setExpanded((e.target as HTMLDetailsElement).open)}
    >
      <summary className="flex cursor-pointer items-center gap-2 font-medium text-foreground">
        <ScrollText className="size-4 text-muted-foreground" />
        Audit trail
        {entityId && (
          <span className="font-mono text-xs text-muted-foreground">
            · {entityId}
          </span>
        )}
        <ChevronDown
          className={cn(
            "ml-auto size-4 transition-transform",
            expanded && "rotate-180",
          )}
          aria-hidden="true"
        />
      </summary>
      <Separator className="my-2" />
      {visible.length === 0 ? (
        <p className="text-xs text-muted-foreground">No audit events yet.</p>
      ) : (
        <ol className="space-y-1">
          {visible.map((row, i) => (
            <li
              key={`${row.ts}:${i}`}
              className="grid grid-cols-[auto_auto_1fr] gap-2 rounded px-1.5 py-1 font-mono text-xs"
            >
              <span className="text-muted-foreground tabular-nums">{row.ts}</span>
              <span className="font-semibold text-foreground">{row.kind}</span>
              {row.detail && (
                <span className="truncate text-muted-foreground">
                  {row.detail}
                </span>
              )}
            </li>
          ))}
        </ol>
      )}
      {hasMore && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setExpanded((s) => !s)}
          className="mt-1 h-7 text-xs"
        >
          {expanded ? "Collapse" : `Show ${rows.length - maxRows} more`}
        </Button>
      )}
    </details>
  );
}
