"use client";

/**
 * SuggestedPostPanel — social-team companion to SuggestedAnglesPanel.
 * Renders LLM-generated post drafts with the Draft watermark + a
 * per-platform target picker (Twitter/X, LinkedIn, Reddit, etc.).
 */

import { Copy, MessageCircle } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export interface SuggestedPost {
  platform: "twitter" | "linkedin" | "reddit" | "generic";
  body: string;
  rationale?: string;
}

export interface SuggestedPostPanelProps {
  posts: SuggestedPost[];
}

const PLATFORM_LABEL: Record<SuggestedPost["platform"], string> = {
  twitter: "X / Twitter",
  linkedin: "LinkedIn",
  reddit: "Reddit",
  generic: "Generic",
};

export function SuggestedPostPanel({ posts }: SuggestedPostPanelProps) {
  const onCopy = (body: string) => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard
        .writeText(body)
        .then(() => toast.success("Post copied"))
        .catch(() => toast.error("Copy failed"));
    }
  };

  return (
    <Card className="relative overflow-hidden">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-6 top-3 select-none rounded bg-warning/10 px-3 py-0.5 text-[10px] font-bold uppercase tracking-[0.2em] text-warning"
      >
        Draft
      </div>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <MessageCircle className="size-4 text-accent" />
          Suggested posts
        </CardTitle>
      </CardHeader>
      <CardContent>
        {posts.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No drafts yet for this topic.
          </p>
        ) : (
          <ol className="space-y-2">
            {posts.map((p, i) => (
              <li
                key={`${p.platform}:${i}`}
                className="group rounded-md border border-border/60 p-3 text-sm"
              >
                <div className="mb-1 flex items-center justify-between">
                  <Badge variant="outline" className="font-mono text-[10px]">
                    {PLATFORM_LABEL[p.platform]}
                  </Badge>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 opacity-0 transition-opacity group-hover:opacity-100"
                    aria-label="Copy post"
                    onClick={() => onCopy(p.body)}
                  >
                    <Copy className="size-3" />
                  </Button>
                </div>
                <p className="whitespace-pre-wrap leading-snug">{p.body}</p>
                {p.rationale && (
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    {p.rationale}
                  </p>
                )}
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
