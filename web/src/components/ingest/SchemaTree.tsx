"use client";

/**
 * SchemaTree — collapsible per-table tree shown on the discover
 * step + the connector dashboard's Schema section.
 *
 * Pure HTML <details> tree (radix-collapsible is overkill); each
 * table shows column rows + a sample-rows preview.
 */

import { ChevronRight, KeyRound, Link2, Table } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export interface SchemaColumn {
  name: string;
  type: string;
  nullable?: boolean;
  is_pk?: boolean;
  is_fk?: boolean;
  sample?: (string | number | null)[];
}

export interface SchemaTable {
  name: string;
  row_count_estimate?: number;
  columns: SchemaColumn[];
  sample_rows?: Record<string, string | number | null>[];
}

export interface SchemaTreeProps {
  tables: SchemaTable[];
  onTableSelect?: (table: SchemaTable) => void;
  className?: string;
}

export function SchemaTree({ tables, onTableSelect, className }: SchemaTreeProps) {
  const [filter, setFilter] = useState("");
  const filtered = filter
    ? tables.filter((t) =>
        t.name.toLowerCase().includes(filter.toLowerCase()),
      )
    : tables;

  if (tables.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        Run discovery to populate the schema.
      </p>
    );
  }

  return (
    <div className={cn("space-y-2", className)}>
      <Input
        type="search"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Filter tables…"
        aria-label="Filter tables"
      />
      <ul className="space-y-1">
        {filtered.map((t) => (
          <li key={t.name}>
            <details className="group rounded-md border border-border bg-surface/40">
              <summary
                className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm hover:bg-surface/60"
                onClick={() => onTableSelect?.(t)}
              >
                <ChevronRight className="size-3.5 shrink-0 text-muted-foreground transition-transform group-open:rotate-90" />
                <Table className="size-3.5 text-info" />
                <span className="font-mono text-xs font-semibold">{t.name}</span>
                {t.row_count_estimate != null && (
                  <Badge variant="outline" className="ml-auto font-mono text-[10px]">
                    {t.row_count_estimate.toLocaleString()} rows
                  </Badge>
                )}
              </summary>
              <ul className="space-y-0.5 px-3 pb-2 text-xs">
                {t.columns.map((c) => (
                  <li
                    key={c.name}
                    className="grid grid-cols-[1fr_auto_auto] items-center gap-2 rounded px-2 py-0.5 hover:bg-surface/40"
                  >
                    <span className="flex items-center gap-1.5 font-mono">
                      {c.is_pk && (
                        <KeyRound
                          className="size-3 text-accent"
                          aria-label="primary key"
                        />
                      )}
                      {c.is_fk && (
                        <Link2 className="size-3 text-info" aria-label="foreign key" />
                      )}
                      {c.name}
                    </span>
                    <span className="font-mono text-[10px] text-muted-foreground">
                      {c.type}
                      {c.nullable === false && " · NN"}
                    </span>
                    {c.sample && c.sample.length > 0 && (
                      <span
                        className="truncate font-mono text-[10px] text-muted-foreground"
                        title={c.sample.map(String).join(", ")}
                      >
                        e.g. {String(c.sample[0])}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </details>
          </li>
        ))}
      </ul>
      {filtered.length === 0 && (
        <p className="text-xs text-muted-foreground">No tables match.</p>
      )}
    </div>
  );
}
