"use client";

/**
 * EnginePickerGrid — `/ingest/new` engine tiles per
 * docs/08-ui/v1.5-redesign/02-data-source-journeys.md + the
 * 06-hero-page-designs.md ingest journey.
 */

import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { EngineIcon, type EngineId } from "@/components/ingest/EngineIcon";
import { TierBadge } from "@/components/shared/TierBadge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface EngineTile {
  id: EngineId;
  title: string;
  blurb: string;
  defaultTier: "L1" | "L2" | "L3" | "L4" | "L5";
  href: string;
}

const TILES: EngineTile[] = [
  {
    id: "postgres",
    title: "PostgreSQL",
    blurb: "Connect a Postgres database. Schema discovery + table mapping.",
    defaultTier: "L2",
    href: "/ingest/new/postgres",
  },
  {
    id: "mysql",
    title: "MySQL",
    blurb: "Same schema-discovery flow as Postgres, with MySQL semantics.",
    defaultTier: "L2",
    href: "/ingest/new/mysql",
  },
  {
    id: "sqlite",
    title: "SQLite",
    blurb: "Point at a `.sqlite` file. Best for the V1 seed corpus.",
    defaultTier: "L2",
    href: "/ingest/new/sqlite",
  },
  {
    id: "neo4j",
    title: "Neo4j",
    blurb: "Bolt protocol. Discovers node labels + relationship types.",
    defaultTier: "L2",
    href: "/ingest/new/neo4j",
  },
  {
    id: "upload",
    title: "Upload files",
    blurb: ".xlsx · .pdf · .csv · .jsonl — wraps the V1 adapters.",
    defaultTier: "L2",
    href: "/ingest/new/upload",
  },
];

export function EnginePickerGrid() {
  return (
    <div
      className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3"
      role="list"
      aria-label="Source engines"
    >
      {TILES.map((t) => (
        <Link
          key={t.id}
          href={t.href}
          role="listitem"
          className={cn(
            "group block transition-transform focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 motion-safe:hover:-translate-y-0.5",
          )}
        >
          <Card className="h-full transition-shadow group-hover:shadow-md">
            <CardContent className="flex flex-col gap-3 p-5">
              <div className="flex items-start justify-between gap-3">
                <EngineIcon engine={t.id} size="md" />
                <TierBadge tier={t.defaultTier} size="sm" detailed={false} />
              </div>
              <div>
                <h3 className="text-base font-semibold text-foreground">{t.title}</h3>
                <p className="mt-1 text-xs text-muted-foreground">{t.blurb}</p>
              </div>
              <div className="mt-auto flex items-center gap-1 text-xs font-medium text-primary opacity-0 transition-opacity group-hover:opacity-100">
                Connect <ArrowRight className="size-3" />
              </div>
            </CardContent>
          </Card>
        </Link>
      ))}
    </div>
  );
}
