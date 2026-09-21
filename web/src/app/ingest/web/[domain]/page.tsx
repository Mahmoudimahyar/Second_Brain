"use client";

/**
 * V1.6a — Domain detail page.
 *
 * Per ui-flow.md §"Page 3 — /ingest/web/[domain]". Header + status pill
 * + Overview tab (settings + budget + recent runs) per the spec; the
 * full History / Pages / Entities / Clusters tabs land in V1.6a
 * follow-up polish (the data exists; this page exposes the most
 * critical surfaces for the Phase 9 Playwright contract).
 */

import { use } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Activity, Database, Network } from "lucide-react";

import { DashboardLayout } from "@/components/layouts/DashboardLayout";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingState } from "@/components/shared/LoadingState";
import { TierBadge } from "@/components/shared/TierBadge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { websiteCrawlApi } from "@/lib/api/client";

export default function DomainDetailPage({
  params,
}: {
  params: Promise<{ domain: string }>;
}) {
  const { domain: domainId } = use(params);
  const id = decodeURIComponent(domainId);

  const domainQ = useQuery({
    queryKey: ["ingest", "web", id],
    queryFn: () => websiteCrawlApi.getDomain(id),
  });
  const jobsQ = useQuery({
    queryKey: ["ingest", "web", id, "jobs"],
    queryFn: () => websiteCrawlApi.listJobs(id),
  });
  const budgetQ = useQuery({
    queryKey: ["ingest", "web", id, "budget"],
    queryFn: () => websiteCrawlApi.getBudget(id),
  });

  if (domainQ.isLoading) return <LoadingState variant="dashboard" />;
  if (domainQ.error) {
    return (
      <ErrorState
        title="Couldn't load domain"
        primaryAction={{ label: "Retry", onClick: () => domainQ.refetch() }}
        technical={String(domainQ.error)}
      />
    );
  }
  const d = domainQ.data;
  if (!d) return null;

  const jobs = jobsQ.data?.jobs ?? [];
  const budget = budgetQ.data;
  const usagePct = budget && budget.cap_usd > 0
    ? Math.round((budget.spent_month_usd / budget.cap_usd) * 100)
    : 0;

  return (
    <DashboardLayout
      title={d.domain}
      description={`Tier ${d.tier} · stage ${d.stage} · ${d.cadence_cron}`}
      breadcrumbs={[
        { label: "Ingest", href: "/ingest" },
        { label: "Website crawls", href: "/ingest/web" },
        { label: d.domain },
      ]}
    >
      <header className="flex flex-wrap items-center gap-2">
        <TierBadge tier={d.tier} size="sm" detailed />
        <Badge variant={d.stage === "L2" ? "warning" : "secondary"} className="font-mono">
          Stage {d.stage}
        </Badge>
        <Badge
          variant={d.status === "active" ? "success" : "secondary"}
          className="font-mono"
        >
          {d.status}
        </Badge>
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Activity className="size-4 text-info" />
              Budget snapshot
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {budget ? (
              <>
                <p>
                  Spent this month:{" "}
                  <strong className="font-mono">
                    ${budget.spent_month_usd.toFixed(2)}
                  </strong>{" "}
                  of ${budget.cap_usd.toFixed(2)}{" "}
                  <span className="text-xs text-muted-foreground">({usagePct}%)</span>
                </p>
                {usagePct >= 80 && (
                  <p className="text-xs text-warning">
                    Approaching budget cap — at 100% the domain auto-pauses.
                  </p>
                )}
              </>
            ) : (
              <LoadingState variant="card-list" rows={1} />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Database className="size-4 text-info" />
              Settings
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-1 text-xs">
            <p><span className="text-muted-foreground">Cadence:</span>{" "}
              <code className="font-mono">{d.cadence_cron}</code></p>
            <p><span className="text-muted-foreground">Pages/run cap:</span>{" "}
              {d.max_pages_per_run.toLocaleString()}</p>
            <p><span className="text-muted-foreground">Pages/month cap:</span>{" "}
              {d.max_pages_per_month.toLocaleString()}</p>
            <p><span className="text-muted-foreground">Concurrency:</span>{" "}
              {d.concurrency}</p>
            <p><span className="text-muted-foreground">OCR:</span>{" "}
              {d.enable_ocr ? "enabled" : "off"}</p>
            <p><span className="text-muted-foreground">ScrapingBee:</span>{" "}
              {d.enable_scrapingbee ? "enabled" : "off"}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Network className="size-4 text-info" />
            Recent crawl jobs
          </CardTitle>
        </CardHeader>
        <CardContent>
          {jobs.length === 0 ? (
            <EmptyState
              title="No crawl runs yet"
              description="The next scheduled run will appear here. Or click Run now from the list page."
              primaryAction={{
                label: "Back to domain list",
                href: "/ingest/web",
              }}
            />
          ) : (
            <ul className="space-y-1.5">
              {jobs.slice(0, 10).map((j) => (
                <li
                  key={j.job_id}
                  className="flex items-center justify-between rounded-md border border-border/60 px-3 py-1.5 text-xs"
                >
                  <span className="font-mono">{j.job_id.slice(0, 16)}</span>
                  <span className="text-muted-foreground">{j.scheduled_at}</span>
                  <Badge
                    variant={
                      j.status === "succeeded" ? "success"
                      : j.status === "failed" ? "destructive"
                      : "secondary"
                    }
                    className="font-mono text-[10px]"
                  >
                    {j.status}
                  </Badge>
                  <span className="font-mono">
                    {j.pages_fetched ?? "—"} pages
                  </span>
                  <span className="font-mono">
                    ${(j.cost_usd ?? 0).toFixed(4)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Link
          href="/ingest/web"
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          ← Back to domain list
        </Link>
      </div>
    </DashboardLayout>
  );
}
