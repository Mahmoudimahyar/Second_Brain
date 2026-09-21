"use client";

/**
 * GraphViewPage — page-level chrome for the three graph views per
 * 06-hero-page-designs.md §5. Sigma canvas + GraphFilters left rail +
 * GraphSelectionPanel right rail + CitationDrawer bottom + LegendPanel
 * collapsible. View-as-table fallback link always available.
 */

import { Suspense, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import { Network, Table } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";

import { Breadcrumbs } from "@/components/shared/Breadcrumbs";
import { CitationDrawer } from "@/components/shared/CitationDrawer";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingState } from "@/components/shared/LoadingState";
import type { GraphLevel } from "@/components/graph/GraphCanvas";
import { GraphFilters, type GraphFiltersState } from "@/components/graph/GraphFilters";
import { GraphResults } from "@/components/graph/GraphResults";
import { GraphSelectionPanel } from "@/components/graph/GraphSelectionPanel";
import { LayoutPicker, type GraphLayout } from "@/components/graph/LayoutPicker";
import { LegendPanel } from "@/components/graph/LegendPanel";
import { MiniMap } from "@/components/graph/MiniMap";
import { PathFinder } from "@/components/graph/PathFinder";

const GraphCanvas = dynamic(
  () => import("@/components/graph/GraphCanvas").then((m) => m.GraphCanvas),
  { ssr: false, loading: () => <LoadingState variant="graph" /> },
);
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { graphApi, type QueryResult } from "@/lib/api/client";

interface Props {
  level: GraphLevel;
  title: string;
  description: string;
}

type LoaderResponse = { results: QueryResult[]; level?: string };

const LEVEL_LOADERS: Record<GraphLevel, (q: string) => Promise<LoaderResponse>> = {
  A: (q) => graphApi.structural(q),
  B: (q) => graphApi.clusters(q),
  C: (q) => graphApi.analyzed(q),
};

export function GraphViewPage(props: Props) {
  return (
    <Suspense fallback={<LoadingState variant="graph" />}>
      <GraphViewPageInner {...props} />
    </Suspense>
  );
}

function GraphViewPageInner({ level, title, description }: Props) {
  const router = useRouter();
  const params = useSearchParams();
  const viewMode = params.get("view") === "table" ? "table" : "canvas";

  const [query, setQuery] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [citationsOpen, setCitationsOpen] = useState(false);
  const [layout, setLayout] = useState<GraphLayout>("force");
  const [filters, setFilters] = useState<GraphFiltersState>({
    sourceTierMin: "all",
    includeAnomalies: false,
  });

  // Cmd-1 / Cmd-2 / Cmd-3 keyboard nav across levels
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA")) return;
      if (e.key === "1") {
        e.preventDefault();
        router.push("/graph/structural");
      } else if (e.key === "2") {
        e.preventDefault();
        router.push("/graph/clusters");
      } else if (e.key === "3") {
        e.preventDefault();
        router.push("/graph/analyzed");
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [router]);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["graph", level, query, filters],
    queryFn: () => LEVEL_LOADERS[level](query),
    enabled: query.length > 0,
  });

  const results = useMemo(() => data?.results ?? [], [data]);
  const selected = useMemo(
    () => results.find((r) => r.node_id === selectedNodeId) ?? null,
    [results, selectedNodeId],
  );

  return (
    <div className="space-y-4">
      <Breadcrumbs items={[{ label: "Graph", href: "/graph/analyzed" }, { label: title }]} />

      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          <p className="text-sm text-muted-foreground">{description}</p>
        </div>
        <Tabs value={`level-${level}`} className="shrink-0">
          <TabsList>
            <TabsTrigger value="level-A" onClick={() => router.push("/graph/structural")}>
              <span className="font-mono text-[10px]">⌘1</span> Structural
            </TabsTrigger>
            <TabsTrigger value="level-B" onClick={() => router.push("/graph/clusters")}>
              <span className="font-mono text-[10px]">⌘2</span> Clusters
            </TabsTrigger>
            <TabsTrigger value="level-C" onClick={() => router.push("/graph/analyzed")}>
              <span className="font-mono text-[10px]">⌘3</span> Analyzed
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <Input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search entities, posts, claims…"
          className="max-w-xl"
          aria-label="Graph search query"
        />
        <div
          role="group"
          aria-label="View mode"
          className="ml-auto inline-flex rounded-md border border-border text-xs"
        >
          <button
            type="button"
            onClick={() => router.push(`?view=canvas`)}
            className={`inline-flex items-center gap-1 rounded-l-md px-2 py-1.5 transition-colors ${
              viewMode === "canvas"
                ? "bg-surface text-foreground font-medium"
                : "text-muted-foreground hover:bg-surface/60"
            }`}
            aria-pressed={viewMode === "canvas"}
          >
            <Network className="size-3.5" />
            Canvas
          </button>
          <button
            type="button"
            onClick={() => router.push(`?view=table`)}
            className={`inline-flex items-center gap-1 rounded-r-md border-l border-border px-2 py-1.5 transition-colors ${
              viewMode === "table"
                ? "bg-surface text-foreground font-medium"
                : "text-muted-foreground hover:bg-surface/60"
            }`}
            aria-pressed={viewMode === "table"}
          >
            <Table className="size-3.5" />
            Table
          </button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)_300px]">
        <aside className="space-y-3">
          <GraphFilters state={filters} onChange={setFilters} />
          <div className="flex items-center justify-between rounded-md border border-border bg-surface/40 px-3 py-2 text-xs">
            <span className="text-muted-foreground">Layout</span>
            <LayoutPicker value={layout} onChange={setLayout} />
          </div>
          <LegendPanel />
          <PathFinder
            onFind={(from, to, depth) => {
              if (from && to) setQuery(`${from} ${to} depth:${depth}`);
            }}
          />
        </aside>

        <section className="min-h-[400px]">
          {isLoading && <LoadingState variant="graph" />}
          {isError && (
            <ErrorState
              title="Query failed"
              technical={(error as Error)?.message}
              primaryAction={{ label: "Retry", onClick: () => refetch() }}
            />
          )}
          {!isLoading && !isError && query.length === 0 && (
            <EmptyState
              icon={<Network className="size-5" />}
              title={`Level ${level} canvas`}
              description="Type a search query above to populate the canvas. The graph store seeds itself once Pass-4 sweeps complete."
            />
          )}
          {!isLoading && results.length > 0 && viewMode === "canvas" && (
            <div className="relative">
              <GraphCanvas
                level={level}
                results={results}
                selectedNodeId={selectedNodeId}
                onSelect={setSelectedNodeId}
              />
              <div className="absolute right-3 top-3 hidden xl:block">
                <MiniMap results={results} />
              </div>
            </div>
          )}
          {!isLoading && results.length > 0 && viewMode === "table" && (
            <GraphResults
              level={level}
              title={title}
              description="Table fallback for accessibility / screen-readers."
            />
          )}
        </section>

        <aside className="space-y-3">
          <GraphSelectionPanel
            result={selected}
            onClear={() => setSelectedNodeId(null)}
            onOpenCitations={() => setCitationsOpen(true)}
          />
        </aside>
      </div>

      <CitationDrawer
        entityId={selected?.node_id ?? null}
        references={selected?.references ?? []}
        open={citationsOpen}
        onOpenChange={setCitationsOpen}
      />
    </div>
  );
}
