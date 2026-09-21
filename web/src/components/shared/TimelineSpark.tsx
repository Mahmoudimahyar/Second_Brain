"use client";

/**
 * Horizontal mini-timeline for selection panels. Dots for events, plus
 * a moving caret for the current moment.
 */

import { useMemo } from "react";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export interface TimelineEvent {
  ts: string; // ISO
  label: string;
  tone?: "default" | "warning" | "destructive" | "success";
}

export interface TimelineSparkProps {
  events: TimelineEvent[];
  current?: string;
  className?: string;
}

const TONE_DOT: Record<NonNullable<TimelineEvent["tone"]>, string> = {
  default: "bg-muted-foreground",
  warning: "bg-warning",
  destructive: "bg-destructive",
  success: "bg-success",
};

export function TimelineSpark({ events, current, className }: TimelineSparkProps) {
  const positions = useMemo(() => {
    if (events.length === 0) return [] as { x: number; ev: TimelineEvent }[];
    const ts = events.map((e) => new Date(e.ts).getTime());
    const min = Math.min(...ts);
    const max = Math.max(...ts);
    const span = Math.max(1, max - min);
    return events.map((ev, i) => ({
      x: ((ts[i] - min) / span) * 100,
      ev,
    }));
  }, [events]);

  const currentX = useMemo(() => {
    if (!current || events.length === 0) return null;
    const ts = events.map((e) => new Date(e.ts).getTime());
    const min = Math.min(...ts);
    const max = Math.max(...ts);
    const span = Math.max(1, max - min);
    const t = new Date(current).getTime();
    return Math.max(0, Math.min(100, ((t - min) / span) * 100));
  }, [current, events]);

  if (events.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">No timeline events yet.</p>
    );
  }

  return (
    <TooltipProvider delayDuration={250}>
      <div className={cn("relative w-full pb-4", className)}>
        <div
          aria-hidden="true"
          className="absolute left-0 right-0 top-2 h-px rounded-full bg-border"
        />
        {positions.map(({ x, ev }, i) => {
          const tone = ev.tone ?? "default";
          return (
            <Tooltip key={`${ev.ts}:${i}`}>
              <TooltipTrigger asChild>
                <span
                  className={cn(
                    "absolute top-1 size-3 -translate-x-1/2 rounded-full ring-2 ring-background",
                    TONE_DOT[tone],
                  )}
                  style={{ left: `${x}%` }}
                  aria-label={`${ev.label} at ${ev.ts}`}
                />
              </TooltipTrigger>
              <TooltipContent>
                <div className="font-medium">{ev.label}</div>
                <div className="font-mono text-[10px] text-muted-foreground">
                  {ev.ts}
                </div>
              </TooltipContent>
            </Tooltip>
          );
        })}
        {currentX != null && (
          <span
            aria-hidden="true"
            className="absolute top-0 h-5 w-px bg-primary"
            style={{ left: `${currentX}%` }}
          />
        )}
      </div>
    </TooltipProvider>
  );
}
