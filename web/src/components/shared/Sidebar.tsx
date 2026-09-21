"use client";

/**
 * Sidebar — per docs/08-ui/v1.5-redesign/01-design-system.md §10 +
 * 06-hero-page-designs.md §1.
 *
 * - Lucide icons per nav item.
 * - Active-state indicator bar (2px indigo) animated between items.
 * - Brand glyph + word mark at top.
 * - Collapsible to icons-only on toggle (next-themes-style persisted state).
 * - Skip-link is the first focusable element (a11y).
 */

import {
  LayoutDashboard,
  Database,
  ShieldCheck,
  Network,
  Users,
  ScrollText,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { motion, useReducedMotion } from "framer-motion";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ComponentType } from "react";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  group?: string;
}

const NAV: NavItem[] = [
  { href: "/", label: "Home", icon: LayoutDashboard, group: "main" },
  { href: "/ingest", label: "Ingest", icon: Database, group: "main" },
  { href: "/hitl", label: "HITL", icon: ShieldCheck, group: "main" },
  { href: "/graph/analyzed", label: "Graph", icon: Network, group: "explore" },
  { href: "/teams/pm", label: "Teams", icon: Users, group: "explore" },
  { href: "/audit", label: "Audit", icon: ScrollText, group: "ops" },
  { href: "/settings/feedback-loop", label: "Settings", icon: Settings, group: "ops" },
];

function isActive(itemHref: string, pathname: string): boolean {
  if (itemHref === "/") return pathname === "/";
  // Normalize: /graph/analyzed should match any /graph/* route
  const base = itemHref.split("/").slice(0, 2).join("/");
  return pathname.startsWith(base);
}

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const reduced = useReducedMotion();

  return (
    <aside
      className={cn(
        "shrink-0 border-r border-border bg-background-warm/50 backdrop-blur",
        "flex flex-col overflow-hidden transition-[width] duration-250 ease-in-out",
        collapsed ? "w-16" : "w-60",
      )}
      aria-label="Primary"
    >
      {/* Skip link */}
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 rounded bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground shadow-md"
      >
        Skip to main content
      </a>

      {/* Brand */}
      <div className="flex h-14 items-center gap-2.5 px-4">
        <div
          aria-hidden="true"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary via-primary to-accent text-primary-foreground shadow-[0_0_0_1px_hsl(var(--primary)/0.3),0_0_12px_-2px_hsl(var(--primary)/0.5)]"
        >
          <span className="text-sm font-bold font-mono">S</span>
        </div>
        {!collapsed && (
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold leading-tight">SecBrain</div>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
              V1.5 · local
            </div>
          </div>
        )}
      </div>

      {/* Nav */}
      <TooltipProvider delayDuration={300}>
        <nav className="flex-1 space-y-1 px-2 py-2">
          {NAV.map((item) => {
            const Icon = item.icon;
            const active = isActive(item.href, pathname);
            const link = (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "group relative flex h-9 items-center gap-3 rounded-md px-2.5 text-sm font-medium transition-colors",
                  active
                    ? "bg-surface text-foreground"
                    : "text-muted-foreground hover:bg-surface/60 hover:text-foreground",
                )}
              >
                {active && !reduced && (
                  <motion.span
                    layoutId="sidebar-active-bar"
                    aria-hidden="true"
                    className="absolute left-0 top-1.5 h-6 w-0.5 rounded-r-full bg-primary"
                    transition={{ type: "spring", stiffness: 380, damping: 30 }}
                  />
                )}
                {active && reduced && (
                  <span
                    aria-hidden="true"
                    className="absolute left-0 top-1.5 h-6 w-0.5 rounded-r-full bg-primary"
                  />
                )}
                <Icon
                  className={cn(
                    "size-4 shrink-0 transition-colors",
                    active ? "text-foreground" : "text-muted-foreground group-hover:text-foreground",
                  )}
                />
                {!collapsed && <span className="truncate">{item.label}</span>}
              </Link>
            );

            if (collapsed) {
              return (
                <Tooltip key={item.href}>
                  <TooltipTrigger asChild>{link}</TooltipTrigger>
                  <TooltipContent side="right">{item.label}</TooltipContent>
                </Tooltip>
              );
            }
            return link;
          })}
        </nav>
      </TooltipProvider>

      {/* Collapse toggle */}
      <div className="border-t border-border p-2">
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          className="flex h-9 w-full items-center gap-3 rounded-md px-2.5 text-sm text-muted-foreground transition-colors hover:bg-surface/60 hover:text-foreground"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-pressed={collapsed}
        >
          {collapsed ? (
            <PanelLeftOpen className="size-4" />
          ) : (
            <PanelLeftClose className="size-4" />
          )}
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
