"use client";

/**
 * ReviewLayout — chrome for HITL pages per 07-component-vocabulary.md
 * §7. The actual `ReviewPage` component composes this; pages that
 * want custom chrome can compose `ReviewLayout` directly.
 */

import type { ReactNode } from "react";

import { Breadcrumbs, type Crumb } from "@/components/shared/Breadcrumbs";
import { ReviewQueueHeader } from "@/components/hitl/ReviewQueueHeader";

export interface ReviewLayoutProps {
  title: string;
  description?: string;
  breadcrumbs?: Crumb[];
  pending: number;
  reviewed?: number;
  bulkMode?: boolean;
  onBulkModeToggle?: (next: boolean) => void;
  children: ReactNode;
}

export function ReviewLayout({
  title,
  description,
  breadcrumbs,
  pending,
  reviewed,
  bulkMode,
  onBulkModeToggle,
  children,
}: ReviewLayoutProps) {
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      {breadcrumbs && breadcrumbs.length > 0 && (
        <Breadcrumbs items={breadcrumbs} />
      )}
      <header className="space-y-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {description && (
            <p className="text-sm text-muted-foreground">{description}</p>
          )}
        </div>
        <ReviewQueueHeader
          title="Queue"
          pending={pending}
          reviewed={reviewed}
          bulkMode={bulkMode}
          onBulkModeToggle={onBulkModeToggle}
        />
      </header>
      <div>{children}</div>
    </div>
  );
}
