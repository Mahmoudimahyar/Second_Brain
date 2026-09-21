"use client";

/**
 * SuggestedAnglesPanel — shared across PM / Social / Marketing per
 * 07-component-vocabulary.md §6. Always shows the "Draft" watermark
 * because the angles are LLM-generated per ADR-016 v2 § (gateway
 * routed via `team_content_angles`).
 */

import { Copy, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

export interface SuggestedAngle {
  angle: string;
  rationale?: string;
  citations?: string[];
  draft_only?: boolean;
}

export interface SuggestedAnglesPanelProps {
  team: "pm" | "social" | "marketing";
  angles: SuggestedAngle[];
}

export function SuggestedAnglesPanel({ team, angles }: SuggestedAnglesPanelProps) {
  const onCopy = (a: SuggestedAngle) => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(a.angle).then(
        () => toast.success("Angle copied to clipboard"),
        () => toast.error("Copy failed — select the text manually"),
      );
    }
  };
  return (
    <Card className="relative overflow-hidden">
      {/* Draft watermark — accessible via aria-hidden + visual */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-6 top-3 select-none rounded bg-warning/10 px-3 py-0.5 text-[10px] font-bold uppercase tracking-[0.2em] text-warning"
      >
        Draft
      </div>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="size-4 text-accent" />
          Suggested angles
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="mb-3 text-[11px] text-muted-foreground">
          LLM-generated via the <code className="font-mono">team_content_angles</code>{" "}
          gateway task (Gemini Flash-Lite per ADR-016 v2). Treat as a draft
          starting point, not a polished output.
        </p>
        <Separator className="mb-3" />
        {angles.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No angles generated yet for this {team} item.
          </p>
        ) : (
          <ol className="space-y-2">
            {angles.map((a, i) => (
              <li
                key={`${a.angle}:${i}`}
                className="group rounded-md border border-border/60 p-3 text-sm"
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="leading-snug">{a.angle}</p>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
                    aria-label="Copy angle to clipboard"
                    onClick={() => onCopy(a)}
                  >
                    <Copy className="size-3.5" />
                  </Button>
                </div>
                {a.rationale && (
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    {a.rationale}
                  </p>
                )}
                {a.citations && a.citations.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {a.citations.slice(0, 3).map((c) => (
                      <Badge
                        key={c}
                        variant="outline"
                        className="font-mono text-[10px]"
                      >
                        {c}
                      </Badge>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
