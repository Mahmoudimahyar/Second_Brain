"use client";

/**
 * V1.6a — Register a new crawl domain.
 *
 * Per ui-flow.md §"Page 2 — /ingest/web/register". Six logical steps
 * presented as collapsible sections on one page so Playwright's
 * happy-path test can fill all fields + submit in one go without
 * driving a multi-step navigator.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { AlertTriangle, Info } from "lucide-react";

import { DashboardLayout } from "@/components/layouts/DashboardLayout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  websiteCrawlApi, type CrawlStage, type CrawlTier,
  type RegisterDomainRequest,
} from "@/lib/api/client";

export default function RegisterDomainPage() {
  const router = useRouter();

  // Form state — flat for Playwright simplicity
  const [domain, setDomain] = useState("");
  const [tier, setTier] = useState<CrawlTier>("L2");
  const [stage, setStage] = useState<CrawlStage>("L1");
  const [cadenceCron, setCadenceCron] = useState("0 6 * * *");
  const [maxUsd, setMaxUsd] = useState(5.0);
  const [maxPagesRun, setMaxPagesRun] = useState(500);
  const [maxPagesMonth, setMaxPagesMonth] = useState(5000);
  const [concurrency, setConcurrency] = useState(4);
  const [enableOcr, setEnableOcr] = useState(false);
  const [enableScrapingbee, setEnableScrapingbee] = useState(false);
  const [confirmL1, setConfirmL1] = useState(false);
  const [notes, setNotes] = useState("");
  const [serverError, setServerError] = useState<string | null>(null);

  const submit = useMutation({
    mutationFn: (payload: RegisterDomainRequest) =>
      websiteCrawlApi.registerDomain(payload),
    onSuccess: (d) => {
      toast.success(`Registered ${d.domain}`);
      router.push(`/ingest/web/${encodeURIComponent(d.domain_id)}?just_registered=1`);
    },
    onError: (err: unknown) => {
      const message =
        (err as { message?: string })?.message
        || "Couldn't register domain";
      setServerError(message);
      toast.error(message);
    },
  });

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setServerError(null);
    submit.mutate({
      domain,
      tier,
      stage,
      cadence_cron: cadenceCron,
      max_pages_per_run: maxPagesRun,
      max_pages_per_month: maxPagesMonth,
      max_usd_per_month: maxUsd,
      concurrency,
      enable_ocr: enableOcr,
      enable_scrapingbee: enableScrapingbee,
      confirm_l1_immutable: confirmL1,
      notes: notes || null,
    });
  }

  return (
    <DashboardLayout
      title="Register a crawl domain"
      description="Step through the form, then submit. Forums + social media are blocked at registration."
      breadcrumbs={[
        { label: "Ingest", href: "/ingest" },
        { label: "Website crawls", href: "/ingest/web" },
        { label: "Register" },
      ]}
    >
      <form onSubmit={onSubmit} className="space-y-4" aria-label="Register crawl domain">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">1. Domain URL</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <Label htmlFor="domain">FQDN (e.g. www.adea.org)</Label>
            <Input
              id="domain"
              required
              placeholder="www.adea.org"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Reddit / SDN / social-media domains are blocked at this step.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">2. Tier</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="tier">Trust tier</Label>
              <Select value={tier} onValueChange={(v) => setTier(v as CrawlTier)}>
                <SelectTrigger id="tier" className="max-w-md">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="L2">L2 — Verified secondary (default)</SelectItem>
                  <SelectItem value="L1">L1 — Canonical truth (immutable; requires confirmation)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {tier === "L1" && (
              <div
                role="region"
                aria-label="L1 tier confirmation"
                className="space-y-2 rounded-md border border-warning/40 bg-warning/5 p-3 text-sm"
              >
                <p className="flex items-center gap-2 text-xs font-medium text-warning">
                  <AlertTriangle className="size-3.5" />
                  L1 sources are treated as immutable ground truth
                </p>
                <p className="text-xs text-muted-foreground">
                  Existing L1 nodes from other sources will not be overwritten.
                  Conflicting L1 claims escalate to HITL.
                </p>
                <label className="flex items-start gap-2 text-xs">
                  <input
                    type="checkbox"
                    className="mt-0.5 size-4"
                    checked={confirmL1}
                    onChange={(e) => setConfirmL1(e.target.checked)}
                    aria-required="true"
                  />
                  <span>I confirm this domain produces immutable ground truth for my domain.</span>
                </label>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">3. Stage</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            <Label htmlFor="stage">Graph stage</Label>
            <Select value={stage} onValueChange={(v) => setStage(v as CrawlStage)}>
              <SelectTrigger id="stage" className="max-w-md">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="L0">L0 — sitemap graph only (free)</SelectItem>
                <SelectItem value="L1">L1 — entity-tagged (~$0 local NLP)</SelectItem>
                <SelectItem value="L2">L2 — full GraphRAG (LLM cost ~$0.001/page)</SelectItem>
              </SelectContent>
            </Select>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">4. Cadence</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <Label htmlFor="cadence_cron">Cron expression</Label>
            <Input
              id="cadence_cron"
              required
              placeholder="0 6 * * *"
              value={cadenceCron}
              onChange={(e) => setCadenceCron(e.target.value)}
              className="font-mono text-xs"
            />
            <p className="text-xs text-muted-foreground">
              Default: <code className="font-mono">0 6 * * *</code> (daily 06:00 UTC).
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">5. Budget + options</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="max_usd_per_month">Monthly $ cap</Label>
              <Input
                id="max_usd_per_month" type="number" step="0.01" min={0} max={10000}
                value={maxUsd}
                onChange={(e) => setMaxUsd(Number(e.target.value))}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="max_pages_per_run">Pages per run cap</Label>
              <Input
                id="max_pages_per_run" type="number" min={1} max={10000}
                value={maxPagesRun}
                onChange={(e) => setMaxPagesRun(Number(e.target.value))}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="max_pages_per_month">Pages per month cap</Label>
              <Input
                id="max_pages_per_month" type="number" min={1} max={1000000}
                value={maxPagesMonth}
                onChange={(e) => setMaxPagesMonth(Number(e.target.value))}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="concurrency">Concurrency (max 16)</Label>
              <Input
                id="concurrency" type="number" min={1} max={16}
                value={concurrency}
                onChange={(e) => setConcurrency(Number(e.target.value))}
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox" checked={enableOcr}
                onChange={(e) => setEnableOcr(e.target.checked)}
              />
              Enable OCR on scanned PDFs (slow)
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox" checked={enableScrapingbee}
                onChange={(e) => setEnableScrapingbee(e.target.checked)}
              />
              Enable ScrapingBee fallback (per-domain opt-in)
            </label>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">6. Notes (optional)</CardTitle>
          </CardHeader>
          <CardContent>
            <Textarea
              placeholder="Why this domain matters for the corpus…"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="min-h-[80px]"
            />
          </CardContent>
        </Card>

        {serverError && (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
          >
            <Info className="size-4 mt-0.5" />
            <span>{serverError}</span>
          </div>
        )}

        <div className="flex items-center justify-end gap-2">
          <Button variant="outline" type="button" onClick={() => router.back()}>
            Cancel
          </Button>
          <Button type="submit" disabled={submit.isPending}>
            {submit.isPending ? "Registering…" : "Register & start first crawl"}
          </Button>
        </div>
      </form>
    </DashboardLayout>
  );
}
