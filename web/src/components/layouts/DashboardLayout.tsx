"use client";

/**
 * DashboardLayout — `max-w-7xl mx-auto` content region with header
 * (breadcrumbs + title + primary action) above the body grid. Per
 * 01-design-system.md §10.
 */

import type { ReactNode } from "react";

import { Breadcrumbs, type Crumb } from "@/components/shared/Breadcrumbs";
import { Button } from "@/components/ui/button";
import Link from "next/link";

export interface DashboardLayoutProps {
  title: string;
  description?: string;
  breadcrumbs?: Crumb[];
  primaryAction?: { label: string; href?: string; onClick?: () => void };
  toolbar?: ReactNode;
  children: ReactNode;
}

export function DashboardLayout({
  title,
  description,
  breadcrumbs,
  primaryAction,
  toolbar,
  children,
}: DashboardLayoutProps) {
  return (
    <div className="mx-auto max-w-7xl space-y-6">
      {breadcrumbs && breadcrumbs.length > 0 && (
        <Breadcrumbs items={breadcrumbs} />
      )}
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {description && (
            <p className="text-sm text-muted-foreground">{description}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {toolbar}
          {primaryAction && (
            primaryAction.href ? (
              <Button asChild>
                <Link href={primaryAction.href}>{primaryAction.label}</Link>
              </Button>
            ) : (
              <Button onClick={primaryAction.onClick}>
                {primaryAction.label}
              </Button>
            )
          )}
        </div>
      </header>
      <div className="space-y-6">{children}</div>
    </div>
  );
}
