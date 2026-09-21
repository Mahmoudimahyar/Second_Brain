"use client";

/**
 * JourneyRail — horizontal step indicator per docs/08-ui/v1.5-redesign/
 * 02-data-source-journeys.md §0 + 07-component-vocabulary.md §2.
 *
 * Pill + connecting line per step. Pulse on active step (reduced-motion
 * snaps to solid glow). Completed steps are clickable links.
 */

import { Check } from "lucide-react";
import { motion, useReducedMotion } from "framer-motion";
import Link from "next/link";

import { cn } from "@/lib/utils";

export type StepStatus = "done" | "active" | "pending";

export interface JourneyStep {
  id: string;
  label: string;
  status: StepStatus;
  href?: string;
}

export interface JourneyRailProps {
  steps: JourneyStep[];
  className?: string;
}

export function JourneyRail({ steps, className }: JourneyRailProps) {
  const reduced = useReducedMotion();
  return (
    <nav
      aria-label="Progress"
      className={cn(
        "flex w-full items-center gap-1 rounded-lg border border-border bg-surface/60 px-3 py-2 text-xs",
        className,
      )}
    >
      <ol className="flex w-full items-center gap-1">
        {steps.map((step, i) => {
          const last = i === steps.length - 1;
          const content = (
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-2 py-1 transition-colors",
                step.status === "active"
                  ? "bg-primary/15 text-foreground font-semibold"
                  : step.status === "done"
                    ? "text-foreground"
                    : "text-muted-foreground",
              )}
            >
              <span
                aria-hidden="true"
                className={cn(
                  "relative inline-flex h-5 w-5 items-center justify-center rounded-full font-mono text-[10px]",
                  step.status === "done"
                    ? "bg-success/20 text-success"
                    : step.status === "active"
                      ? "bg-primary text-primary-foreground"
                      : "bg-surface-elevated text-muted-foreground",
                )}
              >
                {step.status === "active" && !reduced && (
                  <motion.span
                    aria-hidden="true"
                    className="absolute inset-0 rounded-full bg-primary/40"
                    initial={{ scale: 1, opacity: 0.8 }}
                    animate={{ scale: 1.6, opacity: 0 }}
                    transition={{ duration: 1.4, repeat: Infinity, ease: "easeOut" }}
                  />
                )}
                {step.status === "done" ? (
                  <Check className="size-3" />
                ) : (
                  i + 1
                )}
              </span>
              {step.label}
            </span>
          );
          return (
            <li
              key={step.id}
              className="flex flex-1 items-center gap-1"
              aria-current={step.status === "active" ? "step" : undefined}
            >
              {step.href && step.status === "done" ? (
                <Link href={step.href} className="rounded-full hover:bg-surface-elevated">
                  {content}
                </Link>
              ) : (
                content
              )}
              {!last && (
                <span
                  aria-hidden="true"
                  className={cn(
                    "h-px flex-1 rounded-full",
                    step.status === "done"
                      ? "bg-success/40"
                      : "bg-border",
                  )}
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
