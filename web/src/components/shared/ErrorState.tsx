"use client";

import { AlertTriangle } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface ErrorStateAction {
  label: string;
  href?: string;
  onClick?: () => void;
}

export interface ErrorStateProps {
  title?: string;
  description?: string;
  primaryAction?: ErrorStateAction;
  secondaryAction?: ErrorStateAction;
  technical?: string;
  className?: string;
}

function ActionButton({
  action,
  variant = "default",
}: {
  action: ErrorStateAction;
  variant?: "default" | "outline";
}) {
  if (action.href) {
    return (
      <Button asChild variant={variant}>
        <Link href={action.href}>{action.label}</Link>
      </Button>
    );
  }
  return (
    <Button variant={variant} onClick={action.onClick}>
      {action.label}
    </Button>
  );
}

export function ErrorState({
  title = "We couldn't load this",
  description,
  primaryAction,
  secondaryAction,
  technical,
  className,
}: ErrorStateProps) {
  const [showDetails, setShowDetails] = useState(false);

  return (
    <div
      role="alert"
      className={cn(
        "rounded-lg border border-destructive/30 bg-destructive/5 p-6",
        className,
      )}
    >
      <div className="flex items-start gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-destructive/15 text-destructive">
          <AlertTriangle className="size-4" />
        </div>
        <div className="flex-1">
          <h3 className="text-base font-semibold text-foreground">{title}</h3>
          {description && (
            <p className="mt-1 text-sm text-muted-foreground">{description}</p>
          )}
          {(primaryAction || secondaryAction) && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {primaryAction && <ActionButton action={primaryAction} />}
              {secondaryAction && (
                <ActionButton action={secondaryAction} variant="outline" />
              )}
            </div>
          )}
          {technical && (
            <div className="mt-3">
              <button
                type="button"
                onClick={() => setShowDetails((s) => !s)}
                className="text-xs text-muted-foreground hover:text-foreground"
                aria-expanded={showDetails}
              >
                {showDetails ? "Hide" : "Show"} technical details
              </button>
              {showDetails && (
                <pre className="mt-2 max-h-40 overflow-auto rounded bg-surface p-2 text-[11px] font-mono text-muted-foreground">
                  {technical}
                </pre>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
