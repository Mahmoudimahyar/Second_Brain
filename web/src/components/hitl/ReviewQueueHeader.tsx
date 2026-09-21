"use client";

/**
 * ReviewQueueHeader — per-type counts header + bulk-mode toggle per
 * 07-component-vocabulary.md §4.
 */

import { ListChecks } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";

export interface ReviewQueueHeaderProps {
  title: string;
  pending: number;
  reviewed?: number;
  bulkMode?: boolean;
  onBulkModeToggle?: (next: boolean) => void;
}

export function ReviewQueueHeader({
  title,
  pending,
  reviewed = 0,
  bulkMode = false,
  onBulkModeToggle,
}: ReviewQueueHeaderProps) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-3">
      <div>
        <h2 className="flex items-center gap-2 text-base font-semibold">
          <ListChecks className="size-4 text-muted-foreground" />
          {title}
        </h2>
        <p className="text-xs text-muted-foreground">
          <Badge variant="secondary" className="font-mono">
            {pending} pending
          </Badge>
          {reviewed > 0 && (
            <Badge
              variant="success"
              className="ml-1.5 font-mono"
            >
              {reviewed} reviewed
            </Badge>
          )}
        </p>
      </div>
      {onBulkModeToggle && (
        <label className="flex items-center gap-2 text-xs">
          <span className="text-muted-foreground">Bulk mode</span>
          <Switch
            checked={bulkMode}
            onCheckedChange={onBulkModeToggle}
            aria-label="Toggle bulk review mode"
          />
        </label>
      )}
      {!onBulkModeToggle && (
        <Button variant="ghost" size="sm" asChild>
          <a href="/hitl">All queues</a>
        </Button>
      )}
    </header>
  );
}
