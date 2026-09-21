"use client";

/**
 * Mapping wizard — V1.5d C12.
 *
 * Drives the per-table mapping commit flow. Loads suggestions from
 * `/sources/{id}/mapping/suggest` (V1.5a Phase 7), lets the operator
 * edit per-row decisions via `<SchemaMappingTable>`, then posts the
 * decisions to `/sources/{id}/mapping/commit`. The connector's next
 * pull picks up the committed mappings.
 */

import { use, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";

import { DashboardLayout } from "@/components/layouts/DashboardLayout";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingState } from "@/components/shared/LoadingState";
import {
  SchemaMappingTable,
  type MappingDecision,
  type MappingRow,
  type MappingTarget,
} from "@/components/ingest/SchemaMappingTable";
import { Button } from "@/components/ui/button";
import { sourcesApi } from "@/lib/api/client";

type ApiSuggestion = {
  table_or_label: string;
  mapping_type: string;
  target_type: string | null;
  confidence: number;
  routing: string;
};

/** Map backend routing → table decision label. */
function routingToDecision(routing: string): MappingDecision {
  const r = routing.toLowerCase();
  if (r === "auto" || r === "auto_apply") return "auto";
  if (r === "reject" || r === "skip") return "reject";
  return "review";
}

/** Map backend mapping_type → table target kind. */
function typeToKind(mappingType: string): MappingTarget {
  const t = mappingType.toLowerCase();
  if (t.includes("edge") || t === "relation") return "edge";
  if (t === "skip" || t === "ignore") return "skip";
  return "node";
}

export default function MappingWizardPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const sourceId = decodeURIComponent(id);

  // Load suggestions once on mount. The endpoint is POST (per the
  // connector tool contract) so we use a manual one-shot effect rather
  // than a normal GET query.
  const {
    data: suggestion,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ["sources", sourceId, "mapping", "suggest"],
    queryFn: () => sourcesApi.suggestMapping(sourceId),
  });

  const [rows, setRows] = useState<MappingRow[]>([]);

  // Seed local row state from server suggestions whenever they change.
  useEffect(() => {
    if (!suggestion) return;
    setRows(
      (suggestion.per_table as ApiSuggestion[]).map((s) => ({
        source_table: s.table_or_label,
        proposed_target: s.target_type ?? "(none)",
        target_kind: typeToKind(s.mapping_type),
        confidence: s.confidence,
        decision: routingToDecision(s.routing),
      })),
    );
  }, [suggestion]);

  const commitMutation = useMutation({
    mutationFn: () =>
      sourcesApi.commitMapping(
        sourceId,
        rows.map((r) => ({
          table_or_label: r.source_table,
          mapping_type: r.target_kind,
          target_type: r.proposed_target === "(none)" ? null : r.proposed_target,
          suggested_confidence: r.confidence,
          routing: r.decision,
        })),
        false,
      ),
    onSuccess: (res) =>
      toast.success(
        `Mapping committed — ${res.decisions_committed} auto · ${res.decisions_pending_hitl} pending HITL`,
      ),
    onError: (err) => toast.error(`Commit failed: ${String(err)}`),
  });

  const summary = useMemo(() => {
    const counts: Record<MappingDecision, number> = {
      auto: 0, review: 0, reject: 0,
    };
    for (const r of rows) counts[r.decision]++;
    return counts;
  }, [rows]);

  return (
    <DashboardLayout
      title="Schema mapping"
      description={`Review the mapper's proposed source-table → graph-element mapping for ${sourceId}, then commit.`}
      breadcrumbs={[
        { label: "Ingest", href: "/ingest" },
        { label: sourceId, href: `/ingest/sources/${encodeURIComponent(sourceId)}` },
        { label: "Mapping" },
      ]}
      primaryAction={{
        label: commitMutation.isPending ? "Committing…" : `Commit (${summary.auto + summary.review})`,
        onClick: () => commitMutation.mutate(),
      }}
    >
      {isLoading && <LoadingState variant="table" rows={6} cols={4} />}
      {error && (
        <ErrorState
          title="Couldn't load mapping suggestions"
          primaryAction={{ label: "Retry", onClick: () => refetch() }}
          technical={String(error)}
        />
      )}
      {!isLoading && !error && rows.length === 0 && (
        <EmptyState
          title="No tables discovered yet"
          description="Run schema discovery on the source detail page, then return here to map."
          primaryAction={{
            label: "Back to source",
            href: `/ingest/sources/${encodeURIComponent(sourceId)}`,
          }}
        />
      )}
      {rows.length > 0 && (
        <SchemaMappingTable
          rows={rows}
          onRowChange={(idx, next) =>
            setRows((cur) => cur.map((r, i) => (i === idx ? next : r)))
          }
          onBulkAuto={() =>
            setRows((cur) =>
              cur.map((r) =>
                r.confidence >= 0.85 ? { ...r, decision: "auto" } : r,
              ),
            )
          }
          onBulkReject={() =>
            setRows((cur) =>
              cur.map((r) =>
                r.confidence < 0.5 ? { ...r, decision: "reject" } : r,
              ),
            )
          }
          onResetToSuggestions={() => refetch()}
        />
      )}
      {rows.length > 0 && (
        <div className="flex items-center justify-end gap-2 text-xs text-muted-foreground">
          <span>
            {summary.auto} auto · {summary.review} review · {summary.reject} reject
          </span>
          <Button
            size="sm"
            onClick={() => commitMutation.mutate()}
            disabled={commitMutation.isPending}
          >
            {commitMutation.isPending ? "Committing…" : "Commit mapping"}
          </Button>
        </div>
      )}
    </DashboardLayout>
  );
}
