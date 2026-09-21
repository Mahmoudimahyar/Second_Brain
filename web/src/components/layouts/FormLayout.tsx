"use client";

/**
 * FormLayout — `max-w-3xl mx-auto` single-column layout for forms +
 * settings pages. Optional JourneyRail at top.
 */

import type { ReactNode } from "react";

import { Breadcrumbs, type Crumb } from "@/components/shared/Breadcrumbs";
import { JourneyRail, type JourneyStep } from "@/components/shared/JourneyRail";

export interface FormLayoutProps {
  title: string;
  description?: string;
  breadcrumbs?: Crumb[];
  steps?: JourneyStep[];
  children: ReactNode;
}

export function FormLayout({
  title,
  description,
  breadcrumbs,
  steps,
  children,
}: FormLayoutProps) {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {breadcrumbs && breadcrumbs.length > 0 && (
        <Breadcrumbs items={breadcrumbs} />
      )}
      {steps && steps.length > 0 && <JourneyRail steps={steps} />}
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && (
          <p className="text-sm text-muted-foreground">{description}</p>
        )}
      </header>
      <div>{children}</div>
    </div>
  );
}
