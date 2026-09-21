"use client";

/**
 * SchemaMappingTable — per 06-hero-page-designs.md §2 page 3.
 *
 * Lightweight table with editable verdict + per-row tier selector.
 * TanStack Table virtual scroll is the spec stretch but the row
 * count is small enough that a plain table renders cleanly.
 */

import { Sparkles } from "lucide-react";

import { ConfidenceDial } from "@/components/shared/ConfidenceDial";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export type MappingDecision = "auto" | "review" | "reject";
export type MappingTarget = "node" | "edge" | "skip";

export interface MappingRow {
  source_table: string;
  proposed_target: string;
  target_kind: MappingTarget;
  confidence: number;
  decision: MappingDecision;
  reasoning?: string[];
}

export interface SchemaMappingTableProps {
  rows: MappingRow[];
  onRowChange?: (idx: number, next: MappingRow) => void;
  onBulkAuto?: () => void;
  onBulkReject?: () => void;
  onResetToSuggestions?: () => void;
}

const DECISION_VARIANT = {
  auto: { variant: "success" as const, label: "Auto" },
  review: { variant: "warning" as const, label: "Review" },
  reject: { variant: "destructive" as const, label: "Reject" },
};

export function SchemaMappingTable({
  rows,
  onRowChange,
  onBulkAuto,
  onBulkReject,
  onResetToSuggestions,
}: SchemaMappingTableProps) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={onBulkAuto}>
          <Sparkles className="size-3.5" />
          Bulk accept auto
        </Button>
        <Button variant="outline" size="sm" onClick={onBulkReject}>
          Bulk skip reject
        </Button>
        <Button variant="ghost" size="sm" onClick={onResetToSuggestions} className="ml-auto">
          Reset to suggestions
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-surface/40 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-3 py-2">Source table</th>
                <th className="px-3 py-2">Target</th>
                <th className="px-3 py-2 text-center">Confidence</th>
                <th className="px-3 py-2">Decision</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {rows.map((row, i) => (
                <tr key={row.source_table} className="hover:bg-surface/30">
                  <td className="px-3 py-2 font-mono text-xs">
                    {row.source_table}
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant="outline" className="font-mono text-[10px]">
                      {row.target_kind}
                    </Badge>{" "}
                    <span className="ml-1 font-mono text-xs">
                      {row.proposed_target}
                    </span>
                    {row.reasoning && row.reasoning.length > 0 && (
                      <p className="mt-0.5 text-[10px] text-muted-foreground">
                        {row.reasoning[0]}
                      </p>
                    )}
                  </td>
                  <td className="px-3 py-2 text-center">
                    <div className="inline-block">
                      <ConfidenceDial value={row.confidence} size={36} />
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <Select
                      value={row.decision}
                      onValueChange={(v) =>
                        onRowChange?.(i, { ...row, decision: v as MappingDecision })
                      }
                    >
                      <SelectTrigger className="h-8 w-32 text-xs">
                        <SelectValue>
                          <Badge
                            variant={DECISION_VARIANT[row.decision].variant}
                            className="font-mono text-[10px]"
                          >
                            {DECISION_VARIANT[row.decision].label}
                          </Badge>
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        {(["auto", "review", "reject"] as const).map((d) => (
                          <SelectItem key={d} value={d}>
                            {DECISION_VARIANT[d].label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
