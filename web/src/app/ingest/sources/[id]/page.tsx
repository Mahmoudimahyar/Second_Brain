"use client";

import { use } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import Link from "next/link";

import { DashboardLayout } from "@/components/layouts/DashboardLayout";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingState } from "@/components/shared/LoadingState";
import { AuditTrail } from "@/components/shared/AuditTrail";
import { ConnectorHealthCard } from "@/components/ingest/ConnectorHealthCard";
import { CursorEditor } from "@/components/ingest/CursorEditor";
import { SchemaTree, type SchemaTable } from "@/components/ingest/SchemaTree";
import type { EngineId } from "@/components/ingest/EngineIcon";
import type { SourceTier } from "@/components/shared/TierBadge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { sourcesApi } from "@/lib/api/client";

export default function SourceDashboard({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const sourceId = decodeURIComponent(id);
  const queryClient = useQueryClient();

  const sourceQuery = useQuery({
    queryKey: ["source", sourceId],
    queryFn: () => sourcesApi.get(sourceId),
  });

  const pullMutation = useMutation({
    mutationFn: () => sourcesApi.pull(sourceId, "delta"),
    onSuccess: (res) => {
      toast.success(
        `Pull complete — ${res.rows_pulled ?? 0} rows · ${res.status ?? "ok"}`,
      );
      queryClient.invalidateQueries({ queryKey: ["source", sourceId] });
    },
    onError: (err) => toast.error(`Pull failed: ${String(err)}`),
  });

  const discoverMutation = useMutation({
    mutationFn: () => sourcesApi.discover(sourceId),
    onSuccess: (res) =>
      toast.success(`Discovered ${res.tables?.length ?? 0} tables/labels`),
    onError: (err) => toast.error(`Discovery failed: ${String(err)}`),
  });

  if (sourceQuery.isLoading) {
    return <LoadingState variant="dashboard" />;
  }
  if (sourceQuery.error) {
    return (
      <ErrorState
        title="Couldn't load this source"
        description="The connector registry didn't respond."
        primaryAction={{ label: "Retry", onClick: () => sourceQuery.refetch() }}
        secondaryAction={{ label: "Audit log", href: "/audit" }}
        technical={String(sourceQuery.error)}
      />
    );
  }
  if (!sourceQuery.data) {
    return (
      <ErrorState
        title="Source not found"
        description={`No connector registered as ${sourceId}.`}
        primaryAction={{ label: "Back to sources", href: "/ingest" }}
      />
    );
  }

  const source = sourceQuery.data;
  const auditRows = [
    { ts: "now", kind: "connector_view", detail: "viewed via /ingest/sources" },
    ...(source.last_pull_at
      ? [{ ts: source.last_pull_at, kind: "pull_delta", detail: "last pull" }]
      : []),
  ];

  return (
    <DashboardLayout
      title={source.display_name}
      description={`Connector · ${source.engine}`}
      breadcrumbs={[
        { label: "Ingest", href: "/ingest" },
        { label: source.display_name },
      ]}
    >
      {/* Counters come from the backend's aggregate-across-successful-pulls
          query (V1.5d A4). A never-pulled source returns 0s honestly. */}
      <ConnectorHealthCard
        sourceId={source.source_id}
        engine={(source.engine as EngineId) ?? "upload"}
        tier={source.tier as SourceTier}
        status={
          (source.status as "active" | "pulling" | "paused" | "disconnected") ??
          "active"
        }
        lastPullAt={source.last_pull_at ?? null}
        rowsTotal={source.rows_total}
        nodesTotal={source.nodes_total}
        edgesTotal={source.edges_total}
        crossLinks={source.cross_links}
        onPullNow={() => pullMutation.mutate()}
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-start justify-between space-y-0">
            <div>
              <CardTitle className="text-base">Schema</CardTitle>
              <CardDescription>
                Tables / labels + sample rows. Re-discover to refresh, or
                open the mapping wizard to commit table → graph rules.
              </CardDescription>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={discoverMutation.isPending}
                onClick={() => discoverMutation.mutate()}
              >
                {discoverMutation.isPending ? "Discovering…" : "Re-discover"}
              </Button>
              <Button asChild size="sm">
                <Link
                  href={`/ingest/sources/${encodeURIComponent(source.source_id)}/mapping`}
                >
                  Open mapping wizard
                </Link>
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <SchemaTree
              tables={
                (discoverMutation.data?.tables as SchemaTable[] | undefined) ??
                []
              }
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recent activity</CardTitle>
          </CardHeader>
          <CardContent>
            <AuditTrail entityId={source.source_id} rows={auditRows} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Cursors (advanced)</CardTitle>
          <CardDescription>
            Per-table cursor columns the delta-pull tracks. Reset to force a full
            re-pull on the next sweep.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {/* Cursors come from the backend's per-source state row
              (V1.5d A4). Empty list → CursorEditor shows "None tracked yet". */}
          <CursorEditor cursors={source.cursors ?? []} />
        </CardContent>
      </Card>
    </DashboardLayout>
  );
}
