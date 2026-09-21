"use client";

/**
 * GraphSelectionPanel — right-rail detail view per
 * 07-component-vocabulary.md §5. Renders the currently-selected node
 * with TierBadge, properties, TrustMeter (when tier/rank present), +
 * a "View references" button that opens the CitationDrawer.
 */

import { X } from "lucide-react";

import { ProvenancePill, type Rank } from "@/components/shared/ProvenancePill";
import { TrustMeter } from "@/components/shared/TrustMeter";
import { type SourceTier } from "@/components/shared/TierBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { QueryResult } from "@/lib/api/client";

export interface GraphSelectionPanelProps {
  result: QueryResult | null;
  onOpenCitations: () => void;
  onClear: () => void;
}

export function GraphSelectionPanel({
  result,
  onOpenCitations,
  onClear,
}: GraphSelectionPanelProps) {
  if (!result) {
    return (
      <Card className="text-center text-xs text-muted-foreground">
        <CardContent className="p-4">
          Click a node on the canvas to see its details here.
        </CardContent>
      </Card>
    );
  }

  const rank: Rank =
    (result.rank?.toLowerCase() as Rank) === "preferred"
      ? "preferred"
      : (result.rank?.toLowerCase() as Rank) === "deprecated"
        ? "deprecated"
        : "normal";

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between space-y-0">
        <div className="min-w-0">
          <CardTitle className="truncate font-mono text-xs">
            {result.node_id}
          </CardTitle>
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
            {result.node_type}
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={onClear}
          aria-label="Clear selection"
        >
          <X className="size-3.5" />
        </Button>
      </CardHeader>
      <CardContent className="space-y-3 text-xs">
        <ProvenancePill
          tier={result.source_tier as SourceTier}
          rank={rank}
          confidence={result.confidence}
          referenceCount={result.references.length}
          onClickReferences={onOpenCitations}
        />

        <TrustMeter tier={result.source_tier as SourceTier} rank={rank} />

        {Object.keys(result.properties ?? {}).length > 0 && (
          <details className="rounded-md border border-border/50 bg-surface/40 p-2 text-[11px]">
            <summary className="cursor-pointer font-medium">Properties</summary>
            <dl className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
              {Object.entries(result.properties).slice(0, 12).map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-muted-foreground">{k}</dt>
                  <dd className="font-mono truncate" title={String(v)}>
                    {typeof v === "object" ? JSON.stringify(v) : String(v)}
                  </dd>
                </div>
              ))}
            </dl>
          </details>
        )}

        <Button
          variant="outline"
          size="sm"
          className="w-full"
          onClick={onOpenCitations}
        >
          View {result.references.length} reference
          {result.references.length === 1 ? "" : "s"}
        </Button>
      </CardContent>
    </Card>
  );
}
