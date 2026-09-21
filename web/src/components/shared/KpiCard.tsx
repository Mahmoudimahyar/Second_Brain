"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface KpiCardProps {
  label: string;
  value: number | string;
  delta?: { value: number; label?: string; direction?: "up" | "down" };
  icon?: LucideIcon;
  accent?: "primary" | "accent" | "success" | "warning" | "destructive" | "info";
  hint?: string;
  className?: string;
}

function NumberTicker({ value }: { value: number }) {
  const reduced = useReducedMotion();
  const [display, setDisplay] = useState(reduced ? value : 0);

  useEffect(() => {
    if (reduced) {
      setDisplay(value);
      return;
    }
    const start = performance.now();
    const duration = 800;
    let raf = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(Math.round(value * eased));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, reduced]);

  return <span className="tabular-nums">{display.toLocaleString()}</span>;
}

export function KpiCard({
  label,
  value,
  delta,
  icon: Icon,
  accent = "primary",
  hint,
  className,
}: KpiCardProps) {
  const accentClass = {
    primary: "text-primary",
    accent: "text-accent",
    success: "text-success",
    warning: "text-warning",
    destructive: "text-destructive",
    info: "text-info",
  }[accent];

  return (
    <Card
      className={cn(
        "group relative overflow-hidden transition-shadow hover:shadow-md",
        className,
      )}
    >
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-wider text-muted-foreground">
              {Icon && <Icon className={cn("size-3.5", accentClass)} />}
              <span className="truncate">{label}</span>
            </div>
            <div className="mt-1 text-2xl font-semibold tracking-tight kpi-card-number">
              {typeof value === "number" ? <NumberTicker value={value} /> : value}
            </div>
            {(delta || hint) && (
              <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                {delta && (
                  <span
                    className={cn(
                      "inline-flex items-center gap-0.5 font-medium",
                      delta.direction === "up"
                        ? "text-success"
                        : delta.direction === "down"
                          ? "text-destructive"
                          : "text-muted-foreground",
                    )}
                  >
                    {delta.direction === "up" ? "▲" : delta.direction === "down" ? "▼" : "·"}
                    {delta.value > 0 ? `+${delta.value}` : delta.value}
                    {delta.label && ` ${delta.label}`}
                  </span>
                )}
                {hint && <span className="truncate">{hint}</span>}
              </div>
            )}
          </div>
        </div>
        <motion.div
          aria-hidden="true"
          initial={false}
          className="absolute inset-x-0 bottom-0 h-0.5 bg-gradient-to-r from-transparent via-primary/40 to-transparent opacity-0 transition-opacity group-hover:opacity-100"
        />
      </CardContent>
    </Card>
  );
}
