"use client";

/**
 * Home — operational dashboard per docs/08-ui/v1.5-redesign/
 * 06-hero-page-designs.md §1.
 *
 * Cards stagger-fade on first load (100ms each). KPI numbers tick from
 * 0 → target over 800ms via the KpiCard's NumberTicker (reduced-motion
 * snaps to final value).
 */

import { motion, useReducedMotion } from "framer-motion";
import {
  Activity,
  ArrowUpRight,
  Database,
  GitBranch,
  Network,
  Plus,
  ShieldCheck,
  Sparkles,
  Star,
  Users,
} from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/shared/EmptyState";
import { FloatingShapes } from "@/components/shared/FloatingShapes";
import { KpiCard } from "@/components/shared/KpiCard";
import { TierBadge } from "@/components/shared/TierBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

const HITL_QUEUE = [
  { href: "/hitl/alias", label: "Alias", count: 3, tone: "info" as const },
  { href: "/hitl/conflict", label: "Conflicts", count: 2, tone: "warning" as const },
  { href: "/hitl/clusters", label: "Clusters", count: 18, tone: "info" as const },
  { href: "/hitl/proposals", label: "Proposals", count: 7, tone: "info" as const },
  { href: "/hitl/multi-l1", label: "Multi-L1", count: 1, tone: "warning" as const },
  { href: "/hitl/crosslinks", label: "Cross-links", count: 5, tone: "info" as const },
];

const RECENT = [
  { icon: ShieldCheck, label: "Cluster commit", detail: "16 reviewed", time: "8m ago" },
  { icon: ShieldCheck, label: "Proposal accept", detail: "3 accepted", time: "1h ago" },
  { icon: ShieldCheck, label: "Conflict resolved", detail: "1 by L1 priority", time: "2h ago" },
  { icon: Database, label: "Source added", detail: "ds:postgres:partner", time: "4h ago" },
];

const SOURCES = [
  { name: "Official reference data", tier: "L1" as const, status: "active" },
  { name: "r/your_community", tier: "L5" as const, status: "active" },
  { name: "Partner DB", tier: "L2" as const, status: "pulling" },
];

function stagger(delay: number) {
  return { duration: 0.25, ease: [0.16, 1, 0.3, 1] as const, delay };
}

export default function Home() {
  const reduced = useReducedMotion();
  const slot = (i: number) =>
    reduced
      ? { initial: false }
      : {
          initial: { opacity: 0, y: 12 },
          animate: { opacity: 1, y: 0 },
          transition: stagger(i * 0.05),
        };
  const totalHitl = HITL_QUEUE.reduce((acc, q) => acc + q.count, 0);
  return (
    <div className="space-y-6">
      <motion.header {...slot(0)} className="relative flex flex-wrap items-baseline justify-between gap-2 overflow-hidden">
        <div className="relative z-10">
          <h1 className="text-2xl font-semibold tracking-tight">
            Welcome back.
          </h1>
          <p className="text-sm text-muted-foreground">
            Operational overview — pending review, what&apos;s running, recent activity.
          </p>
        </div>
        {/* Aurora-accent floating illustration — decorative, aria-hidden,
            honors prefers-reduced-motion (per FloatingShapes' motion-safe classes). */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-6 -top-10 hidden opacity-70 sm:block"
        >
          <FloatingShapes size="lg" accent="primary" />
        </div>
        <div className="relative z-10 text-xs text-muted-foreground">
          Last sweep: <span className="font-medium text-foreground">2 hours ago</span>
        </div>
      </motion.header>

      {/* KPI row */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <motion.div {...slot(1)}>
          <KpiCard
            label="HITL pending"
            value={totalHitl}
            delta={{ value: 3, label: "since last week", direction: "up" }}
            icon={ShieldCheck}
            accent="warning"
          />
        </motion.div>
        <motion.div {...slot(2)}>
          <KpiCard
            label="Graph nodes"
            value={38037}
            delta={{ value: 412, label: "this week", direction: "up" }}
            icon={Network}
            accent="info"
          />
        </motion.div>
        <motion.div {...slot(3)}>
          <KpiCard
            label="L1 anchors"
            value={124}
            hint="Reference data + Partner DB"
            icon={Star}
            accent="accent"
          />
        </motion.div>
        <motion.div {...slot(4)}>
          <KpiCard
            label="Cost (7d)"
            value="$4.32"
            delta={{ value: -0.12, label: "vs prior 7d", direction: "down" }}
            icon={Sparkles}
            accent="primary"
          />
        </motion.div>
      </div>

      {/* Main grid: HITL inbox + Running now + Recent + Sources */}
      <div className="grid gap-4 lg:grid-cols-3">
        {/* HITL inbox — spans 1 col */}
        <motion.div {...slot(5)} className="lg:row-span-2">
          <Card className="h-full">
            <CardHeader className="flex flex-row items-center justify-between space-y-0">
              <CardTitle className="flex items-center gap-2 text-base">
                <ShieldCheck className="size-4 text-warning" />
                HITL inbox
              </CardTitle>
              <Button asChild variant="ghost" size="sm">
                <Link href="/hitl" className="gap-1">
                  Review <ArrowUpRight className="size-3.5" />
                </Link>
              </Button>
            </CardHeader>
            <CardContent className="space-y-1">
              {HITL_QUEUE.map((q) => (
                <Link
                  key={q.href}
                  href={q.href}
                  className="group flex items-center justify-between rounded-md px-2 py-2 text-sm transition-colors hover:bg-surface-elevated"
                >
                  <span className="flex items-center gap-2">
                    <span
                      aria-hidden="true"
                      className={
                        q.tone === "warning"
                          ? "size-1.5 rounded-full bg-warning"
                          : "size-1.5 rounded-full bg-info"
                      }
                    />
                    {q.label}
                  </span>
                  <Badge
                    variant={q.tone === "warning" ? "warning" : "secondary"}
                    className="font-mono"
                  >
                    {q.count}
                  </Badge>
                </Link>
              ))}
            </CardContent>
          </Card>
        </motion.div>

        {/* Running now */}
        <motion.div {...slot(6)} className="lg:col-span-2">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0">
              <CardTitle className="flex items-center gap-2 text-base">
                <Activity className="size-4 text-info" />
                Running now
              </CardTitle>
              <Badge variant="secondary" className="font-mono">
                1 active
              </Badge>
            </CardHeader>
            <CardContent>
              <div className="rounded-md border border-border bg-background-warm/60 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">Pulling r/your_community</span>
                      <TierBadge tier="L5" size="sm" detailed={false} />
                    </div>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      Pass 4 · sentiment + interview-q · ~3m left · $0.11 / $0.50
                    </p>
                  </div>
                  <Button asChild variant="ghost" size="sm">
                    <Link href="/ingest" className="gap-1">
                      Detail <ArrowUpRight className="size-3.5" />
                    </Link>
                  </Button>
                </div>
                <div
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={62}
                  aria-label="Pass 4 progress"
                  className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-surface"
                >
                  <motion.div
                    initial={reduced ? false : { width: 0 }}
                    animate={{ width: "62%" }}
                    transition={{
                      duration: reduced ? 0 : 0.8,
                      ease: [0.16, 1, 0.3, 1] as const,
                    }}
                    className="h-full rounded-full bg-gradient-to-r from-primary to-accent"
                  />
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* Recent activity */}
        <motion.div {...slot(7)} className="lg:col-span-2">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0">
              <CardTitle className="flex items-center gap-2 text-base">
                <GitBranch className="size-4 text-muted-foreground" />
                Recent activity
              </CardTitle>
              <Button asChild variant="ghost" size="sm">
                <Link href="/audit" className="gap-1">
                  Audit log <ArrowUpRight className="size-3.5" />
                </Link>
              </Button>
            </CardHeader>
            <CardContent>
              <ol className="space-y-2">
                {RECENT.map((r, i) => {
                  const Icon = r.icon;
                  return (
                    <li
                      key={`${r.label}:${i}`}
                      className="flex items-center gap-3 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-surface-elevated"
                    >
                      <Icon className="size-4 shrink-0 text-success" />
                      <div className="min-w-0 flex-1">
                        <span className="font-medium">{r.label}</span>{" "}
                        <span className="text-muted-foreground">— {r.detail}</span>
                      </div>
                      <time className="shrink-0 font-mono text-xs text-muted-foreground">
                        {r.time}
                      </time>
                    </li>
                  );
                })}
              </ol>
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* Sources + quick actions */}
      <div className="grid gap-4 lg:grid-cols-3">
        <motion.div {...slot(8)} className="lg:col-span-2">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0">
              <CardTitle className="flex items-center gap-2 text-base">
                <Database className="size-4 text-muted-foreground" />
                Sources
              </CardTitle>
              <Button asChild variant="outline" size="sm" className="gap-1">
                <Link href="/ingest/new">
                  <Plus className="size-3.5" /> Connect
                </Link>
              </Button>
            </CardHeader>
            <CardContent className="space-y-2">
              {SOURCES.map((s) => (
                <div
                  key={s.name}
                  className="flex items-center justify-between rounded-md border border-border/60 px-3 py-2 text-sm"
                >
                  <span className="flex items-center gap-2">
                    <TierBadge tier={s.tier} size="sm" detailed={false} />
                    <span className="font-medium">{s.name}</span>
                  </span>
                  <Badge
                    variant={s.status === "pulling" ? "warning" : "success"}
                    className="font-mono text-[10px]"
                  >
                    {s.status === "pulling" ? "○ pulling" : "● active"}
                  </Badge>
                </div>
              ))}
              <Separator />
              <p className="text-xs text-muted-foreground">
                3 sources · 38,037 nodes · 71,121 edges · last pull 4h ago
              </p>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div {...slot(9)}>
          <Card className="h-full">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Users className="size-4 text-accent" />
                Top open questions
              </CardTitle>
            </CardHeader>
            <CardContent>
              <EmptyState
                className="border-none bg-transparent py-2 px-0"
                icon={<Sparkles className="size-5" />}
                title="3 high-volume pain points"
                description="Unresolved in PM dashboard. Drill in to see angles."
                primaryAction={{ label: "Open PM dash", href: "/teams/pm" }}
              />
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  );
}
