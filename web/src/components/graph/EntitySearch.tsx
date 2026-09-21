"use client";

/**
 * EntitySearch — alias-aware entity search per 07-component-
 * vocabulary.md §5. Hits the V1 RetrievalService through the
 * existing `/api/v1/graph/analyzed?query=…` route.
 */

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { TierBadge, type SourceTier } from "@/components/shared/TierBadge";
import { ConfidenceChip } from "@/components/shared/ConfidenceChip";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { graphApi } from "@/lib/api/client";

export interface EntitySearchProps {
  /** Optional inline mode for the Cmd-K palette. */
  mode?: "page" | "palette";
  onPick?: (nodeId: string) => void;
}

export function EntitySearch({ mode = "page", onPick }: EntitySearchProps) {
  const router = useRouter();
  const [q, setQ] = useState("");

  const { data } = useQuery({
    queryKey: ["entity-search", q],
    queryFn: () => graphApi.analyzed(q, { limit: 12 }),
    enabled: q.length >= 2,
  });

  const handle = (nodeId: string) => {
    if (onPick) onPick(nodeId);
    else router.push(`/graph/analyzed?query=${encodeURIComponent(nodeId)}`);
  };

  return (
    <div className={mode === "palette" ? "" : "space-y-3"}>
      <Input
        type="search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search entities + aliases (NYU, school:nyu_dental, …)"
        aria-label="Search graph entities"
      />
      {q.length >= 2 && (
        <ul className="space-y-1.5">
          {(data?.results ?? []).map((r) => (
            <li key={r.node_id}>
              <button
                type="button"
                onClick={() => handle(r.node_id)}
                className="w-full text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                <Card className="transition-shadow hover:shadow-md">
                  <CardContent className="flex items-center gap-3 p-3 text-sm">
                    <TierBadge
                      tier={r.source_tier as SourceTier}
                      size="sm"
                      detailed={false}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-semibold">
                        {String(r.properties?.name ?? r.properties?.title ?? r.node_id)}
                      </p>
                      <p className="font-mono text-[10px] text-muted-foreground">
                        {r.node_type} · {r.node_id}
                      </p>
                    </div>
                    <ConfidenceChip value={r.confidence} showLabel={false} />
                  </CardContent>
                </Card>
              </button>
            </li>
          ))}
          {(data?.results ?? []).length === 0 && q.length >= 2 && (
            <li className="text-xs text-muted-foreground">No matches.</li>
          )}
        </ul>
      )}
    </div>
  );
}
