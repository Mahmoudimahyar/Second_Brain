"use client";

import { Breadcrumbs } from "@/components/shared/Breadcrumbs";
import { EntitySearch } from "@/components/graph/EntitySearch";

export default function GraphSearch() {
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <Breadcrumbs
        items={[
          { label: "Graph", href: "/graph/analyzed" },
          { label: "Search" },
        ]}
      />
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Entity search</h1>
        <p className="text-sm text-muted-foreground">
          Full-text + alias-aware lookup across every level. Pick a result to
          jump straight into the Level C view.
        </p>
      </header>
      <EntitySearch />
    </div>
  );
}
