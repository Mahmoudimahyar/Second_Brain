"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { Breadcrumbs } from "@/components/shared/Breadcrumbs";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingState } from "@/components/shared/LoadingState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { hitlApi } from "@/lib/api/client";

export interface ReviewPageProps {
  title: string;
  description?: string;
  itemType: string;
  /** Optional override for the audit-log route key; defaults to itemType. */
  routeKey?: string;
  verdicts: string[];
  /**
   * Optional per-type body renderer. Receives the raw `payload` JSON
   * and returns the rich UI for that item_type. When omitted the
   * generic JSON viewer is rendered.
   */
  renderBody?: (payload: Record<string, unknown>) => ReactNode;
}

export function ReviewPage({
  title,
  description,
  itemType,
  routeKey,
  verdicts,
  renderBody,
}: ReviewPageProps) {
  const effectiveRouteKey = routeKey ?? itemType;
  const queryClient = useQueryClient();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["hitl", itemType],
    queryFn: () => hitlApi.list(itemType, 50),
  });

  const [cursor, setCursor] = useState(0);
  const [notes, setNotes] = useState("");
  const items = data?.items ?? [];
  const current = items[cursor];

  const commit = useMutation({
    mutationFn: ({ id, verdict }: { id: string; verdict: string }) =>
      hitlApi.commit(id, { verdict, notes }),
    onSuccess: (_, vars) => {
      toast.success(`Committed: ${vars.verdict}`, {
        action: {
          label: "Undo",
          onClick: () => toast.message("Undo not yet wired — V1.6"),
        },
        duration: 5000,
      });
      setNotes("");
      queryClient.invalidateQueries({ queryKey: ["hitl", itemType] });
      setCursor((c) => Math.min(items.length - 1, c));
    },
    onError: (err) => toast.error(`Commit failed: ${String(err)}`),
  });

  // J/K keyboard nav
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const inField =
        t &&
        (t.tagName === "INPUT" ||
          t.tagName === "TEXTAREA" ||
          t.isContentEditable);
      if (inField) return;
      if (e.key === "j") {
        e.preventDefault();
        setCursor((c) => Math.min(items.length - 1, c + 1));
      } else if (e.key === "k") {
        e.preventDefault();
        setCursor((c) => Math.max(0, c - 1));
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [items.length]);

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "HITL", href: "/hitl" }, { label: title }]} />
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {description && (
            <p className="text-sm text-muted-foreground">{description}</p>
          )}
        </div>
        {items.length > 0 && (
          <Badge variant="secondary" className="font-mono">
            {cursor + 1} of {items.length}
          </Badge>
        )}
      </header>

      {isLoading && <LoadingState variant="card-list" rows={3} />}

      {error && (
        <ErrorState
          title="Queue failed to load"
          primaryAction={{ label: "Retry", onClick: () => refetch() }}
          technical={String(error)}
        />
      )}

      {data && items.length === 0 && (
        <EmptyState
          icon={<ChevronRight className="size-5" />}
          title="Nothing pending"
          description={`No ${title.toLowerCase()} items in the queue right now.`}
          primaryAction={{ label: "Back to inbox", href: "/hitl" }}
        />
      )}

      {current && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="font-mono text-xs text-muted-foreground">
                {current.item_id}
              </CardTitle>
              <p className="mt-1 text-xs text-muted-foreground">
                {itemType} · status {current.status ?? "pending"}
              </p>
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setCursor((c) => Math.max(0, c - 1))}
                disabled={cursor === 0}
                aria-label="Previous item (K)"
              >
                <ChevronLeft className="size-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setCursor((c) => Math.min(items.length - 1, c + 1))}
                disabled={cursor === items.length - 1}
                aria-label="Next item (J)"
              >
                <ChevronRight className="size-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {renderBody ? (
              renderBody(current.payload as Record<string, unknown>)
            ) : (
              <pre className="max-h-80 overflow-auto rounded-md border border-border bg-background-warm/40 p-3 font-mono text-[11px] text-muted-foreground">
                {JSON.stringify(current.payload, null, 2)}
              </pre>
            )}

            <div className="space-y-2">
              <label className="text-xs font-medium">
                Reviewer notes
                <span className="ml-2 text-muted-foreground">
                  (optional · saved with verdict)
                </span>
              </label>
              <Textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
                placeholder="Explain edge cases the next sweep should learn from…"
                className="text-sm"
              />
            </div>

            <div className="flex flex-wrap gap-2" role="group" aria-label="Verdict actions">
              {verdicts.map((v) => (
                <Button
                  key={v}
                  variant={
                    v.toLowerCase().includes("accept") ||
                    v.toLowerCase().includes("approve")
                      ? "default"
                      : v.toLowerCase().includes("reject") ||
                          v.toLowerCase().includes("cull")
                        ? "destructive"
                        : "outline"
                  }
                  onClick={() =>
                    commit.mutate({ id: current.item_id, verdict: v })
                  }
                  disabled={commit.isPending}
                >
                  {v}
                </Button>
              ))}
              <span className="ml-auto self-center font-mono text-[10px] text-muted-foreground">
                J / K — next / prev
              </span>
            </div>
          </CardContent>
        </Card>
      )}

      <p className="text-[11px] text-muted-foreground">
        Per-type review body for <code className="font-mono">{itemType}</code>{" "}
        ships in V1.5d-W2 as a follow-up — the JSON payload above is the
        fallback view. <code className="font-mono">// TODO: redesign-W2-3</code>
      </p>
      <p className="hidden">{effectiveRouteKey}</p>
    </div>
  );
}
