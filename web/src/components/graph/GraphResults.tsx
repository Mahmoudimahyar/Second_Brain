"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { graphApi, type QueryResult } from "@/lib/api/client";

type Loader = (q: string) => Promise<{ results: QueryResult[] }>;

const LEVEL_LOADERS: Record<"A" | "B" | "C", Loader> = {
  A: (q) => graphApi.structural(q),
  B: (q) => graphApi.clusters(q),
  C: (q) => graphApi.analyzed(q),
};

export function GraphResults({
  level,
  title,
  description,
}: {
  level: "A" | "B" | "C";
  title: string;
  description: string;
}) {
  const [query, setQuery] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["graph", level, query],
    queryFn: () => LEVEL_LOADERS[level](query),
    enabled: query.length > 0,
  });
  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">{title}</h1>
        <p className="text-sm text-gray-500">{description}</p>
      </header>
      <input
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Type a query…"
        className="w-full max-w-xl rounded border border-gray-300 px-3 py-1.5 text-sm"
        aria-label="Graph search query"
      />
      {isLoading && <p>Loading…</p>}
      {data && data.results.length === 0 && query && (
        <p className="text-gray-500">No results.</p>
      )}
      {data && data.results.length > 0 && (
        <ul className="space-y-2 text-sm">
          {data.results.slice(0, 20).map((r) => (
            <li
              key={r.node_id}
              className="rounded border p-2 flex gap-2 items-baseline"
            >
              <span className="font-mono text-xs text-gray-500">
                {r.node_type}
              </span>
              <span className="font-medium">
                {String((r.properties.name ?? r.properties.title ?? r.node_id))}
              </span>
              <span className="ml-auto text-xs">tier {r.source_tier}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-gray-400">
        Sigma.js WebGL canvas ships in V1.5b Phase 3 frontend; this stub
        shows the contracted retrieval payload shape.
      </p>
    </div>
  );
}
