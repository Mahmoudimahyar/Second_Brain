"use client";

/**
 * V1.6a — Website-crawl domain list.
 *
 * Per ui-flow.md §"Page 1 — /ingest/web (domain list)". Shows every
 * registered domain with status, last run, next run, and primary
 * actions (Run now, Pause, Edit, Delete).
 */

import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Activity, Pause, PlayCircle, Plus, Trash2, ExternalLink,
} from "lucide-react";

import { DashboardLayout } from "@/components/layouts/DashboardLayout";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingState } from "@/components/shared/LoadingState";
import { TierBadge } from "@/components/shared/TierBadge";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { websiteCrawlApi, type CrawlDomain } from "@/lib/api/client";

export default function WebsiteCrawlListPage() {
  const qc = useQueryClient();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["ingest", "web", "domains"],
    queryFn: () => websiteCrawlApi.listDomains("active"),
  });

  const runNow = useMutation({
    mutationFn: (id: string) => websiteCrawlApi.runNow(id),
    onSuccess: () => {
      toast.success("Crawl enqueued — dispatcher will pick it up within 5 min");
      qc.invalidateQueries({ queryKey: ["ingest", "web", "domains"] });
    },
    onError: (err) => toast.error(`Couldn't enqueue: ${String(err)}`),
  });
  const pause = useMutation({
    mutationFn: (id: string) => websiteCrawlApi.pause(id),
    onSuccess: () => {
      toast.success("Domain paused");
      qc.invalidateQueries({ queryKey: ["ingest", "web", "domains"] });
    },
  });
  const resume = useMutation({
    mutationFn: (id: string) => websiteCrawlApi.resume(id),
    onSuccess: () => {
      toast.success("Domain resumed");
      qc.invalidateQueries({ queryKey: ["ingest", "web", "domains"] });
    },
  });
  const deleteDomain = useMutation({
    mutationFn: (id: string) => websiteCrawlApi.deleteDomain(id),
    onSuccess: () => {
      toast.success("Domain deleted (audit history preserved)");
      qc.invalidateQueries({ queryKey: ["ingest", "web", "domains"] });
    },
  });

  if (isLoading) return <LoadingState variant="dashboard" />;
  if (error) {
    return (
      <ErrorState
        title="Couldn't load crawl domains"
        primaryAction={{ label: "Retry", onClick: () => refetch() }}
        technical={String(error)}
      />
    );
  }
  const domains = data?.domains ?? [];

  return (
    <DashboardLayout
      title="Website crawls"
      description="User-registered official-source domains. Forums + social media are blocked at registration."
      breadcrumbs={[{ label: "Ingest", href: "/ingest" }, { label: "Website crawls" }]}
      primaryAction={{
        label: "Register domain",
        href: "/ingest/web/register",
      }}
    >
      {domains.length === 0 ? (
        <EmptyState
          title="No crawl domains registered yet"
          description="Register an official-source domain and pick a cadence — V1.6a handles the rest."
          primaryAction={{
            label: "Register your first domain",
            href: "/ingest/web/register",
          }}
        />
      ) : (
        <ul className="space-y-2">
          {domains.map((d) => (
            <DomainRow
              key={d.domain_id}
              domain={d}
              onRunNow={() => runNow.mutate(d.domain_id)}
              onPause={() => pause.mutate(d.domain_id)}
              onResume={() => resume.mutate(d.domain_id)}
              onDelete={() => {
                if (confirm(
                  `Delete '${d.domain}'? Future crawls stop; audit history is preserved.`,
                )) {
                  deleteDomain.mutate(d.domain_id);
                }
              }}
              busy={runNow.isPending || pause.isPending || resume.isPending}
            />
          ))}
        </ul>
      )}
    </DashboardLayout>
  );
}

function DomainRow({
  domain,
  onRunNow,
  onPause,
  onResume,
  onDelete,
  busy,
}: {
  domain: CrawlDomain;
  onRunNow: () => void;
  onPause: () => void;
  onResume: () => void;
  onDelete: () => void;
  busy: boolean;
}) {
  return (
    <li>
      <Card>
        <CardContent className="grid items-center gap-3 p-4 sm:grid-cols-[1fr_auto_auto_auto_auto]">
          <div className="min-w-0">
            <Link
              href={`/ingest/web/${encodeURIComponent(domain.domain_id)}`}
              className="group block"
            >
              <h3 className="truncate text-sm font-semibold transition-colors group-hover:text-primary">
                {domain.domain}
                <ExternalLink className="ml-1 inline size-3 text-muted-foreground" />
              </h3>
              <p className="mt-0.5 text-[11px] text-muted-foreground font-mono">
                {domain.cadence_cron} · stage {domain.stage} · ${" "}
                {domain.max_usd_per_month.toFixed(2)}/mo budget
              </p>
            </Link>
          </div>
          <TierBadge tier={domain.tier} size="sm" detailed={false} />
          <Badge variant={domain.stage === "L2" ? "warning" : "secondary"} className="font-mono text-[10px]">
            {domain.stage}
          </Badge>
          <StatusPill status={domain.status} />
          <div className="flex gap-1">
            <Button
              size="icon" variant="ghost"
              aria-label="Run now" disabled={busy}
              onClick={onRunNow}
            >
              <PlayCircle className="size-4" />
            </Button>
            {domain.status === "active" ? (
              <Button
                size="icon" variant="ghost"
                aria-label="Pause" disabled={busy} onClick={onPause}
              >
                <Pause className="size-4" />
              </Button>
            ) : (
              <Button
                size="icon" variant="ghost"
                aria-label="Resume" disabled={busy} onClick={onResume}
              >
                <Activity className="size-4" />
              </Button>
            )}
            <Button
              size="icon" variant="ghost"
              aria-label="Delete" disabled={busy} onClick={onDelete}
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        </CardContent>
      </Card>
    </li>
  );
}

function StatusPill({ status }: { status: CrawlDomain["status"] }) {
  const variant = status === "active"
    ? "success"
    : status === "auto_paused" ? "destructive"
    : "secondary";
  const label = status === "active" ? "● Active"
    : status === "paused" ? "‖ Paused"
    : status === "auto_paused" ? "✕ Auto-paused"
    : "Deleted";
  return (
    <Badge variant={variant} className="font-mono text-[10px]">
      {label}
    </Badge>
  );
}
