"use client";

import {
  IconBrandMysql,
  IconBrandReact,
  IconUpload,
} from "@tabler/icons-react";
import { Database, Layers3 } from "lucide-react";
import type { ComponentType, ReactNode, SVGProps } from "react";

export type EngineId = "postgres" | "mysql" | "sqlite" | "neo4j" | "upload";

/* Lucide and Tabler have incompatible icon prop types — widen to a
 * generic SVG component so the registry accepts either. */
type AnyIcon = ComponentType<SVGProps<SVGSVGElement>>;

const ENGINE_META: Record<EngineId, {
  Icon: AnyIcon;
  tint: string;
  fg: string;
  ringTint: string;
}> = {
  postgres: {
    Icon: Database as unknown as AnyIcon,
    tint: "bg-info/10",
    fg: "text-info",
    ringTint: "ring-info/20",
  },
  mysql: {
    Icon: IconBrandMysql as unknown as AnyIcon,
    tint: "bg-warning/10",
    fg: "text-warning",
    ringTint: "ring-warning/20",
  },
  sqlite: {
    Icon: Layers3 as unknown as AnyIcon,
    tint: "bg-tier-l2-bg",
    fg: "text-tier-l2",
    ringTint: "ring-tier-l2/30",
  },
  neo4j: {
    Icon: IconBrandReact as unknown as AnyIcon,
    tint: "bg-tier-l3-bg",
    fg: "text-tier-l3",
    ringTint: "ring-tier-l3/30",
  },
  upload: {
    Icon: IconUpload as unknown as AnyIcon,
    tint: "bg-surface-elevated",
    fg: "text-foreground",
    ringTint: "ring-border",
  },
};

export interface EngineIconProps {
  engine: EngineId;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const SIZE: Record<"sm" | "md" | "lg", string> = {
  sm: "h-7 w-7 [&>svg]:size-3.5",
  md: "h-10 w-10 [&>svg]:size-5",
  lg: "h-14 w-14 [&>svg]:size-6",
};

export function EngineIcon({ engine, size = "md", className }: EngineIconProps): ReactNode {
  const meta = ENGINE_META[engine];
  const Icon = meta.Icon;
  return (
    <span
      aria-hidden="true"
      className={`inline-flex items-center justify-center rounded-md ring-1 ${meta.tint} ${meta.fg} ${meta.ringTint} ${SIZE[size]} ${className ?? ""}`}
    >
      <Icon />
    </span>
  );
}
