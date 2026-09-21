"use client";

/**
 * Per-type body for `multi_l1_claims` HITL items per ADR-014 §5 +
 * 06-hero-page-designs.md §4 (variant).
 */

import { ShieldAlert } from "lucide-react";

import { ClaimCard, type Claim } from "@/components/hitl/ClaimCard";
import { Card, CardContent } from "@/components/ui/card";

export interface MultiL1ReviewPayload {
  subject_id: string;
  predicate: string;
  l1_a: Claim;
  l1_b: Claim;
}

export function MultiL1ReviewBody({ payload }: { payload: MultiL1ReviewPayload }) {
  return (
    <div className="space-y-3">
      <div className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/5 p-3 text-sm">
        <ShieldAlert className="mt-0.5 size-4 shrink-0 text-warning" />
        <div>
          <p className="text-xs font-semibold">
            Two L1 sources disagree
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Per ADR-014 §5, multi-L1 collisions never auto-resolve.
            Cross-L1 disagreement is a human-only decision; both anchors
            remain L1.
          </p>
        </div>
      </div>

      <Card>
        <CardContent className="grid gap-2 p-3 text-xs sm:grid-cols-2">
          <div>
            <p className="uppercase tracking-wider text-[10px] text-muted-foreground">
              Subject
            </p>
            <p className="font-mono">{payload.subject_id}</p>
          </div>
          <div>
            <p className="uppercase tracking-wider text-[10px] text-muted-foreground">
              Predicate
            </p>
            <p className="font-mono">{payload.predicate}</p>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-3 sm:grid-cols-2">
        <ClaimCard claim={payload.l1_a} />
        <ClaimCard claim={payload.l1_b} />
      </div>
    </div>
  );
}
