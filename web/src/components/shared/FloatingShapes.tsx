"use client";

/**
 * FloatingShapes — V1.5d C11.
 *
 * Lightweight Aceternity-style hero / empty-state illustration. Three
 * concentric blobs with a subtle floating animation. Honors
 * `prefers-reduced-motion` (the animation simply doesn't apply when
 * the user has the OS-level preference set).
 *
 * No external Aceternity package — Aceternity's published components
 * ship a large dependency surface for what is effectively a few SVG
 * shapes + CSS keyframes. This file does the same shape in ~60 lines
 * with the keyframes already defined in `globals.css` (`@keyframes float`).
 *
 * Use as: <FloatingShapes /> inside an EmptyState `icon` slot, or
 * standalone on the home hero next to copy.
 */

import { cn } from "@/lib/utils";

export interface FloatingShapesProps {
  /** Sizing variant. `sm` for empty-state icon slot, `lg` for hero. */
  size?: "sm" | "lg";
  /** Aurora accent colour (tier or semantic). Falls back to primary. */
  accent?: "primary" | "accent" | "l1" | "l2" | "l3" | "l4" | "l5";
  className?: string;
}

const ACCENT_TO_VAR: Record<NonNullable<FloatingShapesProps["accent"]>, string> = {
  primary: "hsl(var(--primary))",
  accent: "hsl(var(--accent))",
  l1: "hsl(var(--tier-l1))",
  l2: "hsl(var(--tier-l2))",
  l3: "hsl(var(--tier-l3))",
  l4: "hsl(var(--tier-l4))",
  l5: "hsl(var(--tier-l5))",
};

export function FloatingShapes({
  size = "sm",
  accent = "primary",
  className,
}: FloatingShapesProps) {
  const dim = size === "lg" ? 220 : 48;
  const fill = ACCENT_TO_VAR[accent];
  return (
    <svg
      width={dim}
      height={dim}
      viewBox="0 0 100 100"
      aria-hidden="true"
      className={cn("pointer-events-none", className)}
    >
      <defs>
        <radialGradient id={`fs-grad-${accent}`} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor={fill} stopOpacity="0.6" />
          <stop offset="100%" stopColor={fill} stopOpacity="0" />
        </radialGradient>
      </defs>
      <g
        className="motion-safe:animate-[float_4s_ease-in-out_infinite]"
        style={{ transformOrigin: "50% 50%" }}
      >
        <circle cx="50" cy="50" r="34" fill={`url(#fs-grad-${accent})`} />
      </g>
      <g
        className="motion-safe:animate-[float_5s_ease-in-out_infinite]"
        style={{ transformOrigin: "50% 50%", animationDelay: "0.6s" }}
      >
        <circle cx="38" cy="42" r="10" fill={fill} fillOpacity="0.35" />
      </g>
      <g
        className="motion-safe:animate-[float_3.4s_ease-in-out_infinite]"
        style={{ transformOrigin: "50% 50%", animationDelay: "1.2s" }}
      >
        <circle cx="64" cy="58" r="6" fill={fill} fillOpacity="0.55" />
      </g>
    </svg>
  );
}
