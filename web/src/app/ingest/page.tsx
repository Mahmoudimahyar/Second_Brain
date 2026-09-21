"use client";

import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import Link from "next/link";

import { Breadcrumbs } from "@/components/shared/Breadcrumbs";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingState } from "@/components/shared/LoadingState";
import { TierBadge, type SourceTier } from "@/components/shared/TierBadge";
import { EngineIcon, type EngineId } from "@/components/ingest/EngineIcon";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { sourcesApi } from "@/lib/api/client";

export default function IngestHome() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["sources"],
    queryFn: () => sourcesApi.list(false),
  });

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Ingest" }]} />
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Data sources</h1>
          <p className="text-sm text-muted-foreground">
            Every connected database, file source, and forum dump. Each carries a
            trust tier per ADR-014.
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline">
            <Link href="/ingest/web">Website crawls</Link>
          </Button>
          <Button asChild>
            <Link href="/ingest/new">
              <Plus className="size-3.5" />
              New source
            </Link>
          </Button>
        </div>
      </header>

      {isLoading && <LoadingState variant="card-list" rows={3} />}

      {error && (
        <ErrorState
          title="Couldn't load sources"
          description="The connector registry didn't respond. Try again, or check the audit log."
          primaryAction={{ label: "Retry", onClick: () => refetch() }}
          secondaryAction={{ label: "Audit log", href: "/audit" }}
          technical={String(error)}
        />
      )}

      {data && data.connectors.length === 0 && (
        <EmptyState
          icon={<Plus className="size-5" />}
          title="No sources connected yet"
          description="Connect a database, upload a file, or wrap an existing JSONL dump."
          primaryAction={{ label: "Connect a source", href: "/ingest/new" }}
        />
      )}

      {data && data.connectors.length > 0 && (
        <ul className="space-y-2">
          {data.connectors.map((c) => (
            <li key={c.source_id}>
              <Link
                href={`/ingest/sources/${encodeURIComponent(c.source_id)}`}
                className="group block transition-shadow focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                <Card className="transition-shadow group-hover:shadow-md">
                  <CardContent className="flex items-center gap-4 p-4">
                    <EngineIcon
                      engine={(c.engine as EngineId) ?? "upload"}
                      size="md"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="truncate text-sm font-semibold">
                          {c.display_name}
                        </h3>
                        <TierBadge tier={c.tier as SourceTier} size="sm" detailed={false} />
                      </div>
                      <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                        {c.source_id}
                      </p>
                    </div>
                    <div className="hidden text-right text-xs text-muted-foreground sm:block">
                      <Badge
                        variant={
                          c.status === "active"
                            ? "success"
                            : c.status === "pulling"
                              ? "warning"
                              : "secondary"
                        }
                        className="font-mono"
                      >
                        {c.status}
                      </Badge>
                      <div className="mt-0.5">
                        {c.last_pull_at ? (
                          <span className="font-mono">
                            last pull {c.last_pull_at}
                          </span>
                        ) : (
                          "never pulled"
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
