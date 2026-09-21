"use client";

/**
 * LayoutPicker — picks the active Sigma layout (force-directed /
 * hierarchical / radial). Per 07-component-vocabulary.md §5.
 */

import { CircuitBoard, Network, Workflow } from "lucide-react";
import type { ComponentType, SVGProps } from "react";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export type GraphLayout = "force" | "hierarchical" | "radial";

const LAYOUTS: { id: GraphLayout; label: string; Icon: ComponentType<SVGProps<SVGSVGElement>> }[] = [
  { id: "force", label: "Force-directed", Icon: Network },
  { id: "hierarchical", label: "Hierarchical", Icon: Workflow },
  { id: "radial", label: "Radial", Icon: CircuitBoard },
];

export interface LayoutPickerProps {
  value: GraphLayout;
  onChange: (next: GraphLayout) => void;
}

export function LayoutPicker({ value, onChange }: LayoutPickerProps) {
  return (
    <TooltipProvider delayDuration={250}>
      <div
        role="radiogroup"
        aria-label="Canvas layout"
        className="inline-flex rounded-md border border-border bg-surface/40 p-0.5"
      >
        {LAYOUTS.map(({ id, label, Icon }) => (
          <Tooltip key={id}>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className={cn(
                  "h-7 w-7",
                  value === id && "bg-surface-elevated text-foreground shadow",
                )}
                onClick={() => onChange(id)}
                // role="radio" → use aria-checked, NOT aria-pressed. axe
                // rightly flags aria-pressed on radios (it's for toggles).
                aria-label={label}
                role="radio"
                aria-checked={value === id}
              >
                <Icon className="size-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{label}</TooltipContent>
          </Tooltip>
        ))}
      </div>
    </TooltipProvider>
  );
}
