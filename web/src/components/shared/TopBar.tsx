"use client";

/**
 * TopBar — per docs/08-ui/v1.5-redesign/06-hero-page-designs.md §7
 * cross-cutting rules + 01-design-system.md §10.
 *
 * Sticky `h-14` header with: corpus picker · time-range picker ·
 * as-of picker · EntitySearch (Cmd-K) · KbShortcuts (?) · ThemeToggle.
 */

import { Clock, Calendar as CalendarIcon, Database } from "lucide-react";

import { CommandPalette } from "@/components/shared/CommandPalette";
import { KbShortcutsOverlay } from "@/components/shared/KbShortcutsOverlay";
import { ThemeToggle } from "@/components/shared/ThemeToggle";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";

const TIME_RANGES = [
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
  { value: "1y", label: "Last year" },
  { value: "all", label: "All time" },
];

const CORPORA = [
  { value: "v1_seed", label: "v1_seed" },
];

const GLOBAL_SHORTCUTS = [
  { keys: "⌘K / Ctrl+K", label: "Open command palette" },
  { keys: "?", label: "Toggle this overlay" },
  { keys: "g h", label: "Go home" },
  { keys: "g i", label: "Go to ingest" },
  { keys: "g r", label: "Go to HITL review" },
  { keys: "g g", label: "Go to graph viewer" },
  { keys: "g p", label: "Go to PM dashboard" },
  { keys: "Esc", label: "Close modal / clear selection" },
];

export function TopBar() {
  return (
    <header
      className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-background/80 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60"
      role="banner"
    >
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Database className="size-3.5" aria-hidden="true" />
        <span className="sr-only">Corpus:</span>
        <Select defaultValue="v1_seed">
          <SelectTrigger
            className="h-8 w-[140px] border-border bg-transparent text-xs"
            aria-label="Active corpus"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {CORPORA.map((c) => (
              <SelectItem key={c.value} value={c.value}>
                {c.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Separator orientation="vertical" className="h-5" />

      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Clock className="size-3.5" aria-hidden="true" />
        <span className="sr-only">Time range:</span>
        <Select defaultValue="30d">
          <SelectTrigger
            className="h-8 w-[140px] border-border bg-transparent text-xs"
            aria-label="Time range filter"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TIME_RANGES.map((tr) => (
              <SelectItem key={tr.value} value={tr.value}>
                {tr.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Separator orientation="vertical" className="h-5 hidden md:block" />

      <div className="hidden items-center gap-2 text-xs text-muted-foreground md:flex">
        <CalendarIcon className="size-3.5" aria-hidden="true" />
        <span className="text-muted-foreground/80">as-of: now</span>
      </div>

      <div className="ml-auto flex items-center gap-1">
        <CommandPalette />
        <KbShortcutsOverlay shortcuts={GLOBAL_SHORTCUTS} />
        <ThemeToggle />
      </div>
    </header>
  );
}
