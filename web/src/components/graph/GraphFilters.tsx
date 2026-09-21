"use client";

/**
 * GraphFilters — left-rail filter stack per 03-graph-visualization.md
 * + 07-component-vocabulary.md §5.
 *
 * Source-tier minimum, rank checkboxes, include-anomalies toggle.
 * Level-specific filters can be added per-level by the consuming page.
 */

import { Filter } from "lucide-react";

import type { SourceTier } from "@/components/shared/TierBadge";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export interface GraphFiltersState {
  sourceTierMin: SourceTier | "all";
  includeAnomalies: boolean;
}

export interface GraphFiltersProps {
  state: GraphFiltersState;
  onChange: (next: GraphFiltersState) => void;
}

const TIER_OPTIONS: { value: SourceTier | "all"; label: string }[] = [
  { value: "L1", label: "L1 only — canonical truth" },
  { value: "L2", label: "L1 + L2 — verified" },
  { value: "L3", label: "L1–L3 — curated" },
  { value: "L4", label: "L1–L4 — exclude forum" },
  { value: "all", label: "All tiers (incl. L5 forum)" },
];

export function GraphFilters({ state, onChange }: GraphFiltersProps) {
  return (
    <Card className="sticky top-3">
      <CardContent className="space-y-3 p-3">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          <Filter className="size-3.5" />
          Filters
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="tier-min">Source tier</Label>
          <Select
            value={state.sourceTierMin}
            onValueChange={(v) =>
              onChange({
                ...state,
                sourceTierMin: v as SourceTier | "all",
              })
            }
          >
            <SelectTrigger id="tier-min" className="text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TIER_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <label className="flex items-start gap-2 text-xs">
          <input
            type="checkbox"
            className="mt-0.5 size-3.5 rounded border-border accent-primary"
            checked={state.includeAnomalies}
            onChange={(e) =>
              onChange({ ...state, includeAnomalies: e.target.checked })
            }
          />
          <span>Include anomalies (status-flagged edges)</span>
        </label>

        <p className="text-[10px] text-muted-foreground">
          More filters (time range, has citation, rank toggles) wire in
          alongside the Sigma canvas tuning. <code className="font-mono">// TODO: redesign-W3-2</code>
        </p>
      </CardContent>
    </Card>
  );
}
