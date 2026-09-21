"use client";

/**
 * /graph/crosslinks — SAME_AS view per 03-graph-visualization.md §13
 * + 07-component-vocabulary.md §5. Uses the V1.5a CrossGraphLinker
 * output via the existing /api/v1/graph/crosslinks route.
 *
 * Visual treatment: paired source/target with TierBadge + similarity
 * confidence. Sigma canvas variant TODO redesign-W3-3.
 */

import { useQuery } from "@tanstack/react-query";
import { Link as LinkIcon } from "lucide-react";

import { Breadcrumbs } from "@/components/shared/Breadcrumbs";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingState } from "@/components/shared/LoadingState";
import { TierBadge, type SourceTier } from "@/components/shared/TierBadge";
import { Card, CardContent } from "@/components/ui/card";
import { graphApi } from "@/lib/api/client";

export default function CrossLinks() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["graph", "crosslinks"],
    queryFn: () => graphApi.crosslinks(50),
  });

  return (
    <div className="space-y-4">
      <Breadcrumbs
        items={[
          { label: "Graph", href: "/graph/analyzed" },
          { label: "Cross-links" },
        ]}
      />
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Cross-graph links</h1>
        <p className="text-sm text-muted-foreground">
          SAME_AS edges connecting V1.5a connector entities to existing V1 graph anchors.
        </p>
      </header>

      {isLoading && <LoadingState variant="card-list" rows={3} />}

      {error && (
        <ErrorState
          title="Couldn't load cross-links"
          primaryAction={{ label: "Retry", onClick: () => refetch() }}
          technical={String(error)}
        />
      )}

      {data && data.results.length === 0 && (
        <EmptyState
          icon={<LinkIcon className="size-5" />}
          title="No cross-links yet"
          description="Connect a second source (Postgres / Neo4j) — the CrossGraphLinker proposes SAME_AS edges automatically."
          primaryAction={{ label: "Connect a source", href: "/ingest/new" }}
        />
      )}

      {data && data.results.length > 0 && (
        <ul className="space-y-2">
          {data.results.map((r) => (
            <li key={r.node_id}>
              <Card>
                <CardContent className="flex items-center gap-3 p-4 text-sm">
                  <TierBadge tier={r.source_tier as SourceTier} size="sm" detailed={false} />
                  <code className="truncate font-mono text-xs">{r.node_id}</code>
                  <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                    {r.references.length} ref
                    {r.references.length === 1 ? "" : "s"}
                  </span>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}

      <p className="text-[11px] text-muted-foreground">
        A side-by-side review canvas (anchor ↔ candidate) ships in the
        cross-graph HITL flow at <code className="font-mono">/hitl/crosslinks</code>.
        Sigma-mode SAME_AS overlay is <code className="font-mono">// TODO: redesign-W3-3</code>.
      </p>
    </div>
  );
}
