"use client";

import Link from "next/link";

import { Breadcrumbs } from "@/components/shared/Breadcrumbs";
import { EnginePickerGrid } from "@/components/ingest/EnginePickerGrid";
import { Button } from "@/components/ui/button";

export default function NewSource() {
  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Ingest", href: "/ingest" }, { label: "New source" }]} />
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Connect a new source
          </h1>
          <p className="text-sm text-muted-foreground">
            Pick the engine. We&apos;ll discover the schema, suggest a mapping, and
            stream the pull live.
          </p>
        </div>
        <Button asChild variant="ghost" size="sm">
          <Link href="/ingest">All sources</Link>
        </Button>
      </header>

      <EnginePickerGrid />

      <p className="text-xs text-muted-foreground">
        Need a different engine (Snowflake, BigQuery, Discord)? Those land in V1.6.
      </p>
    </div>
  );
}
