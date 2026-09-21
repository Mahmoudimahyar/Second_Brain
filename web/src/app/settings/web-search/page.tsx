"use client";
import { useState } from "react";

export default function WebSearchSettings() {
  const [capUsd, setCapUsd] = useState(5);
  return (
    <div className="space-y-6 max-w-2xl">
      <header>
        <h1 className="text-2xl font-semibold">Web-search providers</h1>
        <p className="text-sm text-gray-500">
          Tavily-only per ADR-016 v2. V1.6 may add Brave / Firecrawl / Exa
          via the `SearchProvider` Protocol.
        </p>
      </header>

      <section className="rounded border p-4 space-y-2">
        <h2 className="font-semibold">Tavily</h2>
        <dl className="grid grid-cols-[150px_1fr] gap-y-1 text-sm">
          <dt className="text-gray-500">API key</dt>
          <dd>
            <code className="text-xs">TAVILY_API_KEY</code>{" "}
            <span className="text-xs text-gray-500">
              env-var — set in <code>.env</code>
            </span>
          </dd>
          <dt className="text-gray-500">Modes</dt>
          <dd>qna_search · search · extract</dd>
        </dl>
      </section>

      <section className="rounded border p-4 space-y-2">
        <h2 className="font-semibold">Cost cap (per corpus per sweep)</h2>
        <div className="flex items-center gap-2 text-sm">
          $
          <input
            type="number"
            value={capUsd}
            min={1}
            step={0.5}
            onChange={(e) => setCapUsd(Number(e.target.value))}
            className="w-24 rounded border px-2 py-1"
          />
          <span className="text-gray-500">USD</span>
        </div>
        {capUsd > 50 && (
          <p className="text-xs text-orange-600">
            ⚠ Caps above $50 require confirmation in production. V1.5 single-user
            allows it.
          </p>
        )}
      </section>

      <section className="rounded border p-4 space-y-2">
        <h2 className="font-semibold">Last 100 calls</h2>
        <p className="text-sm text-gray-500">
          V1.5c ships the cost-tracking schema (
          <code>web_search_cost</code>). The per-call summary table
          renders here once any web-verify run has fired in a live
          sweep.
        </p>
      </section>
    </div>
  );
}
