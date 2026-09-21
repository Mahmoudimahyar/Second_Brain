/**
 * V1.5b API client — thin fetch wrapper around the FastAPI `/api/v1/*`
 * surface. TanStack Query hooks in `hooks.ts` consume this.
 */

const BASE = process.env.NEXT_PUBLIC_API_BASE || "";

export type ApiError = {
  error_code: string;
  message: string;
  context?: Record<string, unknown>;
  retry_safe?: boolean;
};

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${BASE}/api/v1${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init.headers || {}),
    },
    ...init,
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as ApiError;
    throw Object.assign(new Error(body.message || res.statusText), body);
  }
  return res.json() as Promise<T>;
}

// -----------------------------------------------------------------------
// Sources (V1.5a connectors)
// -----------------------------------------------------------------------

export type CursorRow = {
  table: string;
  column: string;
  high_water_mark: string | null;
};

export type ConnectorSummary = {
  source_id: string;
  engine: string;
  display_name: string;
  tier: "L1" | "L2" | "L3" | "L4" | "L5";
  status: string;
  last_pull_at: string | null;
  last_pull_status: string | null;
  /** V1.5d additions — populated by GET /sources/{id} (aggregate stats
   *  across all successful pulls + the per-source cursor listing). */
  rows_total?: number;
  nodes_total?: number;
  edges_total?: number;
  cross_links?: number;
  cursors?: CursorRow[];
};

export const sourcesApi = {
  list: (includeDisconnected = false) =>
    request<{ connectors: ConnectorSummary[] }>(
      `/sources?include_disconnected=${includeDisconnected}`,
    ),
  get: (sourceId: string) =>
    request<ConnectorSummary>(`/sources/${encodeURIComponent(sourceId)}`),
  create: (payload: Record<string, unknown>) =>
    request<ConnectorSummary>("/sources", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  remove: (sourceId: string, retainGraph = true) =>
    request<{ source_id: string; status: string }>(
      `/sources/${encodeURIComponent(sourceId)}?retain_graph=${retainGraph}`,
      { method: "DELETE" },
    ),
  discover: (sourceId: string) =>
    request<{ tables: Array<{ name: string }>; labels: unknown[] }>(
      `/sources/${encodeURIComponent(sourceId)}/discover`,
      { method: "POST" },
    ),
  suggestMapping: (sourceId: string) =>
    request<{
      per_table: Array<{
        table_or_label: string;
        mapping_type: string;
        target_type: string | null;
        confidence: number;
        routing: string;
      }>;
    }>(`/sources/${encodeURIComponent(sourceId)}/mapping/suggest`, {
      method: "POST",
    }),
  commitMapping: (
    sourceId: string,
    decisions: Array<Record<string, unknown>>,
    dryRun = false,
  ) =>
    request<{ decisions_committed: number; decisions_pending_hitl: number }>(
      `/sources/${encodeURIComponent(sourceId)}/mapping/commit?dry_run=${dryRun}`,
      { method: "POST", body: JSON.stringify(decisions) },
    ),
  pull: (sourceId: string, mode: "delta" | "full_resync" = "delta") =>
    request<{
      pull_id: string;
      status: string;
      rows_pulled: number;
      mode: string;
    }>(`/sources/${encodeURIComponent(sourceId)}/pull?mode=${mode}`, {
      method: "POST",
    }),
};

// -----------------------------------------------------------------------
// V1.6a — Website crawl
// -----------------------------------------------------------------------

export type CrawlTier = "L1" | "L2";
export type CrawlStage = "L0" | "L1" | "L2";
export type CrawlStatus = "active" | "paused" | "deleted" | "auto_paused";
export type CrawlJobStatus =
  | "queued" | "running" | "succeeded" | "failed" | "cancelled" | "capped";

export type CrawlDomain = {
  domain_id: string;
  domain: string;
  tier: CrawlTier;
  stage: CrawlStage;
  cadence_cron: string;
  status: CrawlStatus;
  max_pages_per_run: number;
  max_pages_per_month: number;
  max_usd_per_month: number;
  concurrency: number;
  enable_ocr: boolean;
  enable_scrapingbee: boolean;
  confirm_l1: boolean;
  created_at: string;
  updated_at: string;
  created_by: string;
  notes: string | null;
};

export type CrawlJob = {
  job_id: string;
  domain_id: string;
  scheduled_at: string;
  started_at: string | null;
  finished_at: string | null;
  status: CrawlJobStatus;
  trigger: "cron" | "manual" | "force_full_refresh";
  pages_discovered: number | null;
  pages_fetched: number | null;
  pages_unchanged: number | null;
  pages_skipped_robots: number | null;
  pages_skipped_size: number | null;
  pages_blocked: number | null;
  cost_usd: number | null;
  prefect_run_id: string | null;
  error_excerpt: string | null;
};

export type RegisterDomainRequest = {
  domain: string;
  tier?: CrawlTier;
  stage?: CrawlStage;
  cadence_cron?: string;
  max_pages_per_run?: number;
  max_pages_per_month?: number;
  max_usd_per_month?: number;
  concurrency?: number;
  enable_ocr?: boolean;
  enable_scrapingbee?: boolean;
  confirm_l1_immutable?: boolean;
  notes?: string | null;
};

export type BudgetSnapshot = {
  domain_id: string;
  spent_month_usd: number;
  cap_usd: number;
  projected_next_run_usd: number | null;
};

export const websiteCrawlApi = {
  listDomains: (status: string = "active") =>
    request<{ domains: CrawlDomain[]; total: number }>(
      `/ingest/web/domains?status=${status}`,
    ),
  registerDomain: (payload: RegisterDomainRequest) =>
    request<CrawlDomain>("/ingest/web/domains", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getDomain: (domainId: string) =>
    request<CrawlDomain>(
      `/ingest/web/domains/${encodeURIComponent(domainId)}`,
    ),
  pause: (domainId: string) =>
    request<CrawlDomain>(
      `/ingest/web/domains/${encodeURIComponent(domainId)}/pause`,
      { method: "POST" },
    ),
  resume: (domainId: string) =>
    request<CrawlDomain>(
      `/ingest/web/domains/${encodeURIComponent(domainId)}/resume`,
      { method: "POST" },
    ),
  deleteDomain: (domainId: string) =>
    request<CrawlDomain>(
      `/ingest/web/domains/${encodeURIComponent(domainId)}`,
      { method: "DELETE" },
    ),
  runNow: (domainId: string, forceFullRefresh: boolean = false) =>
    request<CrawlJob>(
      `/ingest/web/domains/${encodeURIComponent(domainId)}/run-now`,
      {
        method: "POST",
        body: JSON.stringify({ force_full_refresh: forceFullRefresh }),
      },
    ),
  listJobs: (domainId: string) =>
    request<{ jobs: CrawlJob[]; total: number }>(
      `/ingest/web/domains/${encodeURIComponent(domainId)}/jobs`,
    ),
  getBudget: (domainId: string) =>
    request<BudgetSnapshot>(
      `/ingest/web/domains/${encodeURIComponent(domainId)}/budget`,
    ),
  getBlocklist: () =>
    request<{ forum_domains: string[]; social_domains: string[] }>(
      "/ingest/web/blocklist",
    ),
};

// -----------------------------------------------------------------------
// Graph (V1.5b multi-level retrieval per ADR-012)
// -----------------------------------------------------------------------

export type QueryResult = {
  node_id: string;
  node_type: string;
  properties: Record<string, unknown>;
  source_tier: string;
  rank: string;
  references: string[];
  confidence: number;
  t_valid_from: string | null;
  t_valid_to: string | null;
  path_explanation: Array<Record<string, string>>;
};

export const graphApi = {
  structural: (query: string, opts: { traversalDepth?: number; limit?: number } = {}) =>
    request<{ level: "A"; results: QueryResult[] }>(
      `/graph/structural?query=${encodeURIComponent(query)}&traversal_depth=${
        opts.traversalDepth ?? 2
      }&limit=${opts.limit ?? 50}`,
    ),
  clusters: (query: string, limit = 200) =>
    request<{ level: "B"; results: QueryResult[] }>(
      `/graph/clusters?query=${encodeURIComponent(query)}&limit=${limit}`,
    ),
  analyzed: (query: string, opts: { sourceTierMin?: string; limit?: number } = {}) =>
    request<{ level: "C"; results: QueryResult[] }>(
      `/graph/analyzed?query=${encodeURIComponent(query)}${
        opts.sourceTierMin ? `&source_tier_min=${opts.sourceTierMin}` : ""
      }&limit=${opts.limit ?? 50}`,
    ),
  crosslinks: (limit = 50) =>
    request<{ results: QueryResult[] }>(`/graph/crosslinks?limit=${limit}`),
};

// -----------------------------------------------------------------------
// HITL
// -----------------------------------------------------------------------

export const hitlApi = {
  inbox: () =>
    request<{ counts: Record<string, number>; total: number }>(
      "/hitl/inbox",
    ),
  list: (itemType: string, limit = 20) =>
    request<{
      items: Array<{
        item_id: string;
        item_type: string;
        payload: Record<string, unknown>;
        status: string;
      }>;
    }>(`/hitl/${encodeURIComponent(itemType)}?limit=${limit}`),
  commit: (
    itemId: string,
    body: {
      verdict: string;
      notes?: string;
      extra?: Record<string, unknown>;
      escalate?: boolean;
    },
  ) =>
    request<{ item_id: string; status: string; verdict: string }>(
      `/hitl/${encodeURIComponent(itemId)}/commit`,
      { method: "POST", body: JSON.stringify(body) },
    ),
};

// -----------------------------------------------------------------------
// Settings (feedback loop policy)
// -----------------------------------------------------------------------

export const settingsApi = {
  feedbackLoop: (corpusId: string, promptTemplateId: string) =>
    request<{
      examples: Array<{ pattern: string; selection_score: number }>;
      blocklist: Array<{ pattern: string; hit_count: number }>;
      context_hash: string;
      feedback_log_count: number;
    }>(
      `/settings/feedback-loop?corpus_id=${encodeURIComponent(
        corpusId,
      )}&prompt_template_id=${encodeURIComponent(promptTemplateId)}`,
    ),
  appendDecision: (payload: Record<string, unknown>) =>
    request<{ feedback_id: string; verdict: string }>(
      "/settings/feedback-loop/decisions",
      { method: "POST", body: JSON.stringify(payload) },
    ),
  policy: () =>
    request<{
      weights: Record<string, number>;
      caps: { positive_examples_k: number; blocklist_max: number };
    }>("/settings/feedback-loop/policy"),
  corpora: () =>
    request<{
      corpora: Array<{ corpus_id: string; decision_count: number }>;
    }>("/settings/corpora"),
};

// -----------------------------------------------------------------------
// Audit
// -----------------------------------------------------------------------

export const auditApi = {
  list: (filters: { kind?: string; sourceId?: string; limit?: number } = {}) =>
    request<{ entries: Array<Record<string, unknown>>; total_returned: number }>(
      `/audit?${[
        filters.kind && `kind=${encodeURIComponent(filters.kind)}`,
        filters.sourceId && `source_id=${encodeURIComponent(filters.sourceId)}`,
        filters.limit && `limit=${filters.limit}`,
      ]
        .filter(Boolean)
        .join("&")}`,
    ),
};
