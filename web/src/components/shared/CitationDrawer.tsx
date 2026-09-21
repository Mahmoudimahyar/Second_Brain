"use client";

/**
 * CitationDrawer — bottom drawer for `references` per docs/08-ui/
 * v1.5-redesign/07-component-vocabulary.md §2. Slides up from the
 * bottom on every page where an entity can be selected.
 */

import { ExternalLink, FileText } from "lucide-react";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Separator } from "@/components/ui/separator";

export interface CitationDrawerProps {
  entityId?: string | null;
  references: string[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function refIsUrl(r: string): boolean {
  return /^https?:\/\//i.test(r);
}

export function CitationDrawer({
  entityId,
  references,
  open,
  onOpenChange,
}: CitationDrawerProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="bottom" className="h-[50vh] overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <FileText className="size-4 text-muted-foreground" />
            References
            {entityId && (
              <span className="font-mono text-xs text-muted-foreground">
                · {entityId}
              </span>
            )}
          </SheetTitle>
          <SheetDescription>
            Provenance trail for the selected entity. Each reference points
            back to the source row, post, or page it came from.
          </SheetDescription>
        </SheetHeader>
        <Separator className="my-3" />
        {references.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No references attached.
          </p>
        ) : (
          <ol className="space-y-1.5">
            {references.map((ref) => (
              <li
                key={ref}
                className="flex items-center justify-between gap-2 rounded-md border border-border/50 px-3 py-2 text-sm transition-colors hover:bg-surface-elevated"
              >
                <span className="min-w-0 truncate font-mono text-xs">
                  {ref}
                </span>
                {refIsUrl(ref) && (
                  <a
                    href={ref}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-muted-foreground hover:text-foreground"
                    aria-label={`Open ${ref} in a new tab`}
                  >
                    <ExternalLink className="size-3.5" />
                  </a>
                )}
              </li>
            ))}
          </ol>
        )}
      </SheetContent>
    </Sheet>
  );
}
