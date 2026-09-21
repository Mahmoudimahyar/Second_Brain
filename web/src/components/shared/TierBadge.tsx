"use client";

/**
 * TierBadge — per docs/08-ui/v1.5-redesign/05-trust-tier-ux.md §1.
 *
 * Color + glyph + label so the tier is never communicated by color alone
 * (WCAG 2.1 AA per docs/08-ui/v1.5-redesign/09-accessibility.md §2).
 */

import { Star, BookOpen, Bookmark, Globe, MessageCircle } from "lucide-react";
import type { ComponentType } from "react";

import { Badge, type BadgeProps } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export type SourceTier = "L1" | "L2" | "L3" | "L4" | "L5";

interface TierMeta {
  glyph: ComponentType<{ className?: string }>;
  label: string;
  short: string;
  description: string;
  badgeVariant: BadgeProps["variant"];
}

const TIER: Record<SourceTier, TierMeta> = {
  L1: {
    glyph: Star,
    label: "Canonical truth",
    short: "L1",
    description:
      "Ground-truth source. Immutable; existing L1 anchors not overwritten.",
    badgeVariant: "l1",
  },
  L2: {
    glyph: BookOpen,
    label: "Verified secondary",
    short: "L2",
    description: "Curated source; can be re-pulled.",
    badgeVariant: "l2",
  },
  L3: {
    glyph: Bookmark,
    label: "Curated community",
    short: "L3",
    description: "Reviewed community contributions.",
    badgeVariant: "l3",
  },
  L4: {
    glyph: Globe,
    label: "Raw web",
    short: "L4",
    description: "Crawled web content; low trust.",
    badgeVariant: "l4",
  },
  L5: {
    glyph: MessageCircle,
    label: "Forum / social",
    short: "L5",
    description: "Individual forum / social posts; high volume, low per-claim trust.",
    badgeVariant: "l5",
  },
};

const SIZE: Record<"sm" | "md" | "lg", string> = {
  sm: "text-[11px] py-0 px-1.5 [&>svg]:size-3",
  md: "text-xs px-2 [&>svg]:size-3.5",
  lg: "text-sm py-1 px-2.5 [&>svg]:size-4",
};

export interface TierBadgeProps {
  tier: SourceTier;
  size?: "sm" | "md" | "lg";
  iconOnly?: boolean;
  detailed?: boolean;
  className?: string;
}

export function TierBadge({
  tier,
  size = "md",
  iconOnly = false,
  detailed = true,
  className,
}: TierBadgeProps) {
  const meta = TIER[tier];
  const Glyph = meta.glyph;

  const badge = (
    <Badge
      variant={meta.badgeVariant}
      role="status"
      aria-label={`Source tier ${tier} — ${meta.label}`}
      className={cn(SIZE[size], className)}
    >
      <Glyph aria-hidden="true" className="inline-block" />
      {!iconOnly && <span className="font-semibold">{meta.short}</span>}
    </Badge>
  );

  if (!detailed) return badge;

  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip>
        <TooltipTrigger asChild>{badge}</TooltipTrigger>
        <TooltipContent>
          <div className="font-medium">
            {tier} — {meta.label}
          </div>
          <div className="max-w-[220px] text-muted-foreground">
            {meta.description}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
