"use client";

/**
 * ConnectorHealthCard — KPI card for `/ingest/sources/[id]`.
 */

import { motion, useReducedMotion } from "framer-motion";
import { Activity, Pause, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

import { TierBadge, type SourceTier } from "@/components/shared/TierBadge";
import { EngineIcon, type EngineId } from "@/components/ingest/EngineIcon";

export interface ConnectorHealthCardProps {
  sourceId: string;
  engine: EngineId;
  tier: SourceTier;
  status: "active" | "pulling" | "paused" | "disconnected";
  lastPullAt?: string | null;
  /** Pass `undefined` (or omit) when the backend hasn't shipped the
   *  counter yet — the metric renders an em-dash. Pass `0` only when
   *  the connector genuinely has zero rows/nodes/etc. */
  rowsTotal?: number;
  nodesTotal?: number;
  edgesTotal?: number;
  crossLinks?: number;
  onPullNow?: () => void;
}

const STATUS_VARIANT = {
  active: { variant: "success" as const, label: "● Active" },
  pulling: { variant: "warning" as const, label: "○ Pulling" },
  paused: { variant: "secondary" as const, label: "‖ Paused" },
  disconnected: { variant: "destructive" as const, label: "✕ Disconnected" },
};

function Metric({
  label,
  value,
}: {
  label: string;
  value: number | string | undefined;
}) {
  const display =
    value === undefined
      ? "—"
      : typeof value === "number"
        ? value.toLocaleString()
        : value;
  return (
    <div className="space-y-0.5">
      <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">
        {label}
      </dt>
      <dd
        className="font-mono text-base font-semibold tabular-nums"
        title={value === undefined ? "Backend has not shipped this counter yet" : undefined}
      >
        {display}
      </dd>
    </div>
  );
}

export function ConnectorHealthCard({
  sourceId,
  engine,
  tier,
  status,
  lastPullAt,
  rowsTotal,
  nodesTotal,
  edgesTotal,
  crossLinks,
  onPullNow,
}: ConnectorHealthCardProps) {
  const reduced = useReducedMotion();
  const meta = STATUS_VARIANT[status];
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between space-y-0">
        <div className="flex items-center gap-3">
          <EngineIcon engine={engine} size="lg" />
          <div>
            <CardTitle className="font-mono text-sm">{sourceId}</CardTitle>
            <p className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
              <TierBadge tier={tier} size="sm" detailed={false} />
              <span>·</span>
              {lastPullAt ? (
                <span>
                  Last pull{" "}
                  <time className="font-mono">{lastPullAt}</time>
                </span>
              ) : (
                <span>Never pulled</span>
              )}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={meta.variant} className="font-mono">
            {meta.label}
          </Badge>
          {status === "pulling" && !reduced && (
            <motion.span
              aria-hidden="true"
              className="inline-flex items-center"
              animate={{ rotate: 360 }}
              transition={{ duration: 1.6, repeat: Infinity, ease: "linear" }}
            >
              <Activity className="size-3.5 text-warning" />
            </motion.span>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Metric label="Rows" value={rowsTotal} />
          <Metric label="Nodes" value={nodesTotal} />
          <Metric label="Edges" value={edgesTotal} />
          <Metric label="Cross-links" value={crossLinks} />
        </dl>
        <Separator className="my-4" />
        <div className="flex flex-wrap items-center gap-2">
          <Button
            onClick={onPullNow}
            disabled={status === "pulling" || status === "disconnected"}
            size="sm"
          >
            <RefreshCw className="size-3.5" />
            {status === "pulling" ? "Pull running…" : "Pull now"}
          </Button>
          <Button size="sm" variant="outline" disabled>
            <Pause className="size-3.5" />
            Pause schedule
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
