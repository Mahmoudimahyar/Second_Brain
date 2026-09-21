"use client";

import { useQuery } from "@tanstack/react-query";
import {
  GitMerge,
  Layers,
  Link as LinkIcon,
  ListChecks,
  Scale,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import Link from "next/link";

import { Breadcrumbs } from "@/components/shared/Breadcrumbs";
import { LoadingState } from "@/components/shared/LoadingState";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { hitlApi } from "@/lib/api/client";

interface HitlType {
  id: string;
  routeKey: string;
  label: string;
  description: string;
  icon: typeof ShieldCheck;
  tone?: "warning" | "info" | "default";
}

const TYPES: HitlType[] = [
  {
    id: "alias",
    routeKey: "alias",
    label: "Alias review",
    description: "Mention ↔ canonical entity matches in the 0.75–0.90 confidence band.",
    icon: GitMerge,
    tone: "info",
  },
  {
    id: "conflict",
    routeKey: "conflict",
    label: "Conflict review",
    description: "Trust-tier clashes; system suggests winner, you confirm.",
    icon: Scale,
    tone: "warning",
  },
  {
    id: "cluster_review",
    routeKey: "clusters",
    label: "Cluster cull",
    description: "Approve, cull, merge, or split the Pass-3 clusters before Pass 4.",
    icon: Layers,
    tone: "info",
  },
  {
    id: "node_edge_proposal",
    routeKey: "proposals",
    label: "Node/edge proposals",
    description: "New type proposals from Pass 4 + the feedback loop.",
    icon: Sparkles,
    tone: "info",
  },
  {
    id: "multi_l1_claims",
    routeKey: "multi-l1",
    label: "Multi-L1 collision",
    description: "Two L1 sources disagree on the same fact.",
    icon: ShieldAlert,
    tone: "warning",
  },
  {
    id: "cross_graph_link",
    routeKey: "crosslinks",
    label: "Cross-graph link",
    description: "Connector entity ↔ existing entity matches.",
    icon: LinkIcon,
    tone: "info",
  },
  {
    id: "judge_disagreement",
    routeKey: "judge",
    label: "Judge disagreement",
    description: "Three-vendor LLM judges split; human tie-break.",
    icon: ShieldCheck,
    tone: "warning",
  },
  {
    id: "escalated",
    routeKey: "escalated",
    label: "Escalated",
    description: "Anything someone deferred up to you specifically.",
    icon: ListChecks,
    tone: "default",
  },
];

export default function HITLInbox() {
  const { data, isLoading } = useQuery({
    queryKey: ["hitl", "inbox"],
    queryFn: () => hitlApi.inbox(),
    refetchInterval: 30_000,
  });

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "HITL" }]} />
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            HITL inbox
          </h1>
          <p className="text-sm text-muted-foreground">
            Everything queued for human review. Click any tile to start a session.
          </p>
        </div>
        {data && (
          <Badge variant="secondary" className="font-mono">
            {data.total} pending
          </Badge>
        )}
      </header>

      {isLoading && <LoadingState variant="card-list" rows={4} />}

      {data && (
        <ul
          className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3"
          role="list"
        >
          {TYPES.map((t) => {
            const Icon = t.icon;
            const count = data.counts[t.id] ?? 0;
            const tone = t.tone ?? "default";
            return (
              <li key={t.id}>
                <Link
                  href={`/hitl/${t.routeKey}`}
                  className="group block focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                >
                  <Card className="h-full transition-shadow group-hover:shadow-md motion-safe:group-hover:-translate-y-0.5 motion-safe:transition-transform">
                    <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-2">
                      <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                        <Icon
                          className={
                            tone === "warning"
                              ? "size-4 text-warning"
                              : tone === "info"
                                ? "size-4 text-info"
                                : "size-4 text-muted-foreground"
                          }
                        />
                        {t.label}
                      </CardTitle>
                      <Badge
                        variant={
                          count > 0
                            ? tone === "warning"
                              ? "warning"
                              : "secondary"
                            : "outline"
                        }
                        className="font-mono"
                      >
                        {count}
                      </Badge>
                    </CardHeader>
                    <CardContent className="pt-0 text-xs text-muted-foreground">
                      {t.description}
                    </CardContent>
                  </Card>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
