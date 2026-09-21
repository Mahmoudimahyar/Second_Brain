"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ScrollText } from "lucide-react";

import { Breadcrumbs } from "@/components/shared/Breadcrumbs";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingState } from "@/components/shared/LoadingState";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { auditApi } from "@/lib/api/client";

export default function AuditLog() {
  const [kind, setKind] = useState("");
  const [sourceId, setSourceId] = useState("");
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["audit", kind, sourceId],
    queryFn: () =>
      auditApi.list({
        kind: kind || undefined,
        sourceId: sourceId || undefined,
        limit: 100,
      }),
  });

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Audit" }]} />
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Audit log</h1>
        <p className="text-sm text-muted-foreground">
          Every connector + UI action writes a row here. Forensic interface —
          minimal motion, fast filters.
        </p>
      </header>

      <Card>
        <CardContent className="grid gap-3 p-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="kind-filter">Kind</Label>
            <Input
              id="kind-filter"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              placeholder="connector_connect, ui_view, …"
              className="font-mono text-xs"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="source-filter">Source ID</Label>
            <Input
              id="source-filter"
              value={sourceId}
              onChange={(e) => setSourceId(e.target.value)}
              placeholder="ds:postgres:partner"
              className="font-mono text-xs"
            />
          </div>
        </CardContent>
      </Card>

      {isLoading && <LoadingState variant="table" rows={8} cols={6} />}

      {error && (
        <ErrorState
          title="Couldn't load audit log"
          primaryAction={{ label: "Retry", onClick: () => refetch() }}
          technical={String(error)}
        />
      )}

      {data && data.entries.length === 0 && (
        <EmptyState
          icon={<ScrollText className="size-5" />}
          title="No matching audit rows"
          description="Try clearing filters, or trigger an action (connect a source, commit a HITL item) to see it appear here."
        />
      )}

      {data && data.entries.length > 0 && (
        <Card>
          <CardContent className="p-0">
            <table className="w-full text-xs">
              <thead className="border-b border-border bg-surface/40 text-left uppercase tracking-wider text-[10px] text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">ID</th>
                  <th className="px-3 py-2">Kind</th>
                  <th className="px-3 py-2">Source</th>
                  <th className="px-3 py-2">Actor</th>
                  <th className="px-3 py-2">Outcome</th>
                  <th className="px-3 py-2">TS</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {data.entries.map((row, i) => {
                  const k = String(row.kind ?? "");
                  return (
                    <tr key={i} className="transition-colors hover:bg-surface/40">
                      <td className="px-3 py-1.5 font-mono text-[11px] text-muted-foreground">
                        {String(row.audit_id ?? "")}
                      </td>
                      <td className="px-3 py-1.5">
                        <Badge
                          variant={k.startsWith("ui_") ? "secondary" : "outline"}
                          className="font-mono"
                        >
                          {k}
                        </Badge>
                      </td>
                      <td className="px-3 py-1.5 font-mono text-[11px]">
                        {String(row.source_id ?? "—")}
                      </td>
                      <td className="px-3 py-1.5">{String(row.actor ?? "")}</td>
                      <td className="px-3 py-1.5">
                        <Badge
                          variant={
                            row.outcome === "ok"
                              ? "success"
                              : row.outcome === "error"
                                ? "destructive"
                                : "secondary"
                          }
                          className="font-mono"
                        >
                          {String(row.outcome ?? "")}
                        </Badge>
                      </td>
                      <td className="px-3 py-1.5 font-mono text-[11px] text-muted-foreground">
                        {String(row.ts ?? "")}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
