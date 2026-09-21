"use client";

/**
 * CommandPalette — global Cmd-K palette per docs/08-ui/v1.5-redesign/
 * 07-component-vocabulary.md §2.
 *
 * Sections:
 *  - Pages (route navigation)
 *  - Actions (theme toggle, etc.)
 *
 * The full entity-search section (graph search via /api/v1/graph/search)
 * is built in W3 alongside the graph canvas. TODO: redesign-W3-1.
 */

import {
  LayoutDashboard,
  Database,
  ShieldCheck,
  Network,
  Users,
  ScrollText,
  Settings,
  Moon,
  Sun,
  Search,
} from "lucide-react";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from "@/components/ui/command";
import { Button } from "@/components/ui/button";

const PAGES = [
  { href: "/", label: "Home", icon: LayoutDashboard, hint: "g h" },
  { href: "/ingest", label: "Ingest sources", icon: Database, hint: "g i" },
  { href: "/hitl", label: "HITL review", icon: ShieldCheck, hint: "g r" },
  { href: "/graph/analyzed", label: "Graph viewer", icon: Network, hint: "g g" },
  { href: "/teams/pm", label: "PM dashboard", icon: Users, hint: "g p" },
  { href: "/audit", label: "Audit log", icon: ScrollText, hint: "g a" },
  { href: "/settings/feedback-loop", label: "Settings", icon: Settings },
];

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const { theme, setTheme } = useTheme();

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const navigate = (href: string) => {
    setOpen(false);
    router.push(href);
  };

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        className="hidden gap-2 px-3 text-muted-foreground md:flex"
        aria-label="Open command palette (Cmd-K)"
      >
        <Search className="size-3.5" />
        <span className="text-xs">Search…</span>
        <span className="ml-2 rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-[10px]">
          ⌘K
        </span>
      </Button>
      <Button
        variant="ghost"
        size="icon"
        onClick={() => setOpen(true)}
        className="md:hidden"
        aria-label="Open command palette"
      >
        <Search className="size-4" />
      </Button>
      <CommandDialog open={open} onOpenChange={setOpen}>
        <CommandInput placeholder="Type a command or search…" />
        <CommandList>
          <CommandEmpty>No results found.</CommandEmpty>
          <CommandGroup heading="Pages">
            {PAGES.map((p) => {
              const Icon = p.icon;
              return (
                <CommandItem
                  key={p.href}
                  value={p.label}
                  onSelect={() => navigate(p.href)}
                >
                  <Icon className="size-4" />
                  <span>{p.label}</span>
                  {p.hint && <CommandShortcut>{p.hint}</CommandShortcut>}
                </CommandItem>
              );
            })}
          </CommandGroup>
          <CommandSeparator />
          <CommandGroup heading="Actions">
            <CommandItem
              onSelect={() => {
                setTheme(theme === "dark" ? "light" : "dark");
                setOpen(false);
              }}
            >
              {theme === "dark" ? (
                <Sun className="size-4" />
              ) : (
                <Moon className="size-4" />
              )}
              <span>Toggle theme</span>
            </CommandItem>
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </>
  );
}
