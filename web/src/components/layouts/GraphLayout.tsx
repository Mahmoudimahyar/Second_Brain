"use client";

/**
 * GraphLayout — full-width layout used by graph views. 3-col grid
 * [filters | canvas | selection].
 */

import type { ReactNode } from "react";

export interface GraphLayoutProps {
  filters: ReactNode;
  canvas: ReactNode;
  selection?: ReactNode;
  drawer?: ReactNode;
}

export function GraphLayout({ filters, canvas, selection, drawer }: GraphLayoutProps) {
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)_300px]">
        <aside className="space-y-3">{filters}</aside>
        <section className="min-h-[400px]">{canvas}</section>
        <aside className="space-y-3">{selection}</aside>
      </div>
      {drawer}
    </div>
  );
}
