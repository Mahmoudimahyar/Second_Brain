"use client";

/**
 * EscalationActionRow — bottom-of-card row per 07-component-
 * vocabulary.md §4 for HITL flows that need escalate + defer +
 * commit-next-item in a single bar.
 */

import { ArrowUpRight, ChevronLeft, ChevronRight, Clock } from "lucide-react";

import { Button } from "@/components/ui/button";

export interface EscalationActionRowProps {
  onPrev?: () => void;
  onNext?: () => void;
  onDefer?: () => void;
  onEscalate?: () => void;
  disabled?: boolean;
}

export function EscalationActionRow({
  onPrev,
  onNext,
  onDefer,
  onEscalate,
  disabled = false,
}: EscalationActionRowProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3 text-xs">
      <Button variant="ghost" size="sm" onClick={onPrev} disabled={disabled || !onPrev}>
        <ChevronLeft className="size-3.5" />
        Previous
      </Button>
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={onDefer} disabled={disabled || !onDefer}>
          <Clock className="size-3.5" />
          Defer
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={onEscalate}
          disabled={disabled || !onEscalate}
        >
          <ArrowUpRight className="size-3.5" />
          Escalate
        </Button>
        <Button
          size="sm"
          onClick={onNext}
          disabled={disabled || !onNext}
        >
          Commit + next
          <ChevronRight className="size-3.5" />
        </Button>
      </div>
    </div>
  );
}
