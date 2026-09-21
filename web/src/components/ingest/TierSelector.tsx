"use client";

/**
 * TierSelector — per docs/08-ui/v1.5-redesign/05-trust-tier-ux.md §5
 *
 * Radix Select for the tier dropdown + an inline confirmation
 * checkbox that appears when the user picks L1 (per ADR-014).
 */

import { useState } from "react";

import {
  TierBadge,
  type SourceTier,
} from "@/components/shared/TierBadge";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

export interface TierSelectorProps {
  value: SourceTier;
  onChange: (tier: SourceTier) => void;
  confirmL1: boolean;
  onConfirmL1Change: (confirmed: boolean) => void;
  id?: string;
  className?: string;
}

const TIERS: { tier: SourceTier; label: string; hint: string }[] = [
  { tier: "L1", label: "L1 — Canonical truth", hint: "Immutable ground truth (requires confirmation)" },
  { tier: "L2", label: "L2 — Verified secondary", hint: "Curated, re-pullable (default)" },
  { tier: "L3", label: "L3 — Curated community", hint: "Reviewed community contributions" },
  { tier: "L4", label: "L4 — Raw web", hint: "Crawled web content" },
  { tier: "L5", label: "L5 — Forum / social", hint: "Individual forum or social posts" },
];

export function TierSelector({
  value,
  onChange,
  confirmL1,
  onConfirmL1Change,
  id = "tier",
  className,
}: TierSelectorProps) {
  return (
    <div className={cn("space-y-2", className)}>
      <div className="space-y-1.5">
        <Label htmlFor={id}>Source tier</Label>
        <Select
          value={value}
          onValueChange={(v) => {
            onChange(v as SourceTier);
            onConfirmL1Change(false);
          }}
        >
          <SelectTrigger id={id} className="max-w-md">
            <SelectValue>
              <span className="inline-flex items-center gap-2">
                <TierBadge tier={value} size="sm" detailed={false} />
                <span>{TIERS.find((t) => t.tier === value)?.label}</span>
              </span>
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {TIERS.map((t) => (
              <SelectItem key={t.tier} value={t.tier}>
                <span className="inline-flex items-center gap-2">
                  <TierBadge tier={t.tier} size="sm" detailed={false} />
                  <span>{t.label}</span>
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          {TIERS.find((t) => t.tier === value)?.hint}
        </p>
      </div>

      {value === "L1" && (
        <ConfirmL1Card checked={confirmL1} onCheckedChange={onConfirmL1Change} />
      )}
    </div>
  );
}

function ConfirmL1Card({
  checked,
  onCheckedChange,
}: {
  checked: boolean;
  onCheckedChange: (v: boolean) => void;
}) {
  // Native checkbox to avoid adding @radix-ui/react-checkbox markup overhead
  // for this single use; it's a controlled boolean.
  const [touched, setTouched] = useState(false);
  return (
    <div
      role="region"
      aria-label="L1 tier confirmation"
      className="space-y-2 rounded-md border border-warning/40 bg-warning/5 p-3 text-sm"
    >
      <p className="text-xs font-medium text-warning">
        L1 sources are treated as immutable ground truth
      </p>
      <p className="text-xs text-muted-foreground">
        Existing L1 nodes from other sources will not be overwritten by this
        connector. If two L1 sources disagree on the same fact, the conflict is
        escalated to HITL.
      </p>
      <label className="flex items-start gap-2 text-xs">
        <input
          type="checkbox"
          className="mt-0.5 size-4 rounded border-border bg-surface accent-primary"
          checked={checked}
          onChange={(e) => {
            onCheckedChange(e.target.checked);
            setTouched(true);
          }}
          aria-required="true"
          aria-invalid={touched && !checked}
        />
        <span>
          I confirm this data source is immutable ground truth for my domain.
        </span>
      </label>
    </div>
  );
}
