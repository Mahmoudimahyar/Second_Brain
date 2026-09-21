"use client";

/**
 * TeamDashboardLayout — shared chrome for PM / Social / Marketing per
 * 07-component-vocabulary.md §6.
 */

import type { ReactNode } from "react";

import { Breadcrumbs } from "@/components/shared/Breadcrumbs";

export interface TeamDashboardLayoutProps {
  team: "pm" | "social" | "marketing";
  title: string;
  description?: string;
  kpiStrip?: ReactNode;
  toolbar?: ReactNode;
  children: ReactNode;
}

const TEAM_LABEL = {
  pm: "PM",
  social: "Social",
  marketing: "Marketing",
} as const;

export function TeamDashboardLayout({
  team,
  title,
  description,
  kpiStrip,
  toolbar,
  children,
}: TeamDashboardLayoutProps) {
  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Teams" }, { label: TEAM_LABEL[team] }]} />
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {description && (
            <p className="text-sm text-muted-foreground">{description}</p>
          )}
        </div>
        {toolbar}
      </header>

      {kpiStrip && <div>{kpiStrip}</div>}

      <div>{children}</div>
    </div>
  );
}
