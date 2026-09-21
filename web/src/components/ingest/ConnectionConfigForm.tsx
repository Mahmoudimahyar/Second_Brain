"use client";

/**
 * ConnectionConfigForm — common chrome around per-engine forms per
 * 07-component-vocabulary.md §3.
 *
 * Engine-specific forms compose this shell. JourneyRail at the top,
 * a 2-col grid (form | preview), and a sticky footer with primary +
 * cancel actions.
 */

import Link from "next/link";
import type { ReactNode } from "react";

import { JourneyRail, type JourneyStep } from "@/components/shared/JourneyRail";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

const DEFAULT_STEPS: JourneyStep[] = [
  { id: "intake", label: "Intake", status: "active" },
  { id: "discover", label: "Discover", status: "pending" },
  { id: "mapping", label: "Mapping", status: "pending" },
  { id: "verify", label: "Verify", status: "pending" },
  { id: "live", label: "Live", status: "pending" },
];

export interface ConnectionConfigFormProps {
  title: string;
  description?: string;
  cancelHref?: string;
  submitting?: boolean;
  submitLabel?: string;
  error?: string | null;
  preview?: ReactNode;
  children: ReactNode;
  onSubmit: () => void;
  steps?: JourneyStep[];
}

export function ConnectionConfigForm({
  title,
  description,
  cancelHref = "/ingest/new",
  submitting = false,
  submitLabel = "Continue",
  error = null,
  preview,
  children,
  onSubmit,
  steps = DEFAULT_STEPS,
}: ConnectionConfigFormProps) {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
      className="space-y-6"
    >
      <JourneyRail steps={steps} />

      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && (
          <p className="text-sm text-muted-foreground">{description}</p>
        )}
      </header>

      <div className="grid gap-6 lg:grid-cols-[1fr_minmax(0,360px)]">
        <Card>
          <CardContent className="space-y-4 p-5">{children}</CardContent>
        </Card>
        {preview && (
          <aside className="space-y-4">{preview}</aside>
        )}
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive"
        >
          {error}
        </div>
      )}

      <div className="sticky bottom-0 -mx-2 flex flex-wrap items-center justify-between gap-2 rounded-t-lg border-t border-border bg-background/80 px-2 py-3 backdrop-blur">
        <Button asChild variant="ghost">
          <Link href={cancelHref}>Cancel</Link>
        </Button>
        <Button type="submit" disabled={submitting}>
          {submitting ? "Connecting…" : submitLabel}
        </Button>
      </div>
    </form>
  );
}
