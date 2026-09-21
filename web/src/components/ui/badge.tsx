import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary text-primary-foreground shadow",
        secondary:
          "border-transparent bg-surface text-foreground",
        destructive:
          "border-transparent bg-destructive/15 text-destructive",
        success:
          "border-transparent bg-success/15 text-success",
        warning:
          "border-transparent bg-warning/15 text-warning",
        outline: "text-foreground border-border",
        l1: "border-tier-l1/30 bg-tier-l1-bg text-tier-l1-fg",
        l2: "border-tier-l2/30 bg-tier-l2-bg text-tier-l2-fg",
        l3: "border-tier-l3/30 bg-tier-l3-bg text-tier-l3-fg",
        l4: "border-tier-l4/30 bg-tier-l4-bg text-tier-l4-fg",
        l5: "border-tier-l5/30 bg-tier-l5-bg text-tier-l5-fg",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
