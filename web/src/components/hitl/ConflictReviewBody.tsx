"use client";

/**
 * Per-type body for `conflict` HITL items per 06-hero-page-designs.md §4
 * + 05-trust-tier-ux.md §7. Two ClaimCards side-by-side + system
 * resolution banner + audit trail.
 */

import { Scale } from "lucide-react";

import { AuditTrail } from "@/components/shared/AuditTrail";
import { ClaimCard, type Claim } from "@/components/hitl/ClaimCard";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

export interface ConflictReviewPayload {
  subject_id: string;
  predicate: string;
  detected_ts?: string;
  claim_a: Claim;
  claim_b: Claim;
  system_resolution?: "a_wins" | "b_wins" | "split" | "hitl";
  resolution_reason?: string;
}

export function ConflictReviewBody({ payload }: { payload: ConflictReviewPayload }) {
  const aWins = payload.system_resolution === "a_wins";
  const bWins = payload.system_resolution === "b_wins";
  return (
    <div className="space-y-3">
      <Card>
        <CardContent className="grid gap-2 p-3 text-xs sm:grid-cols-3">
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
          <div>
            <p className="uppercase tracking-wider text-[10px] text-muted-foreground">
              Detected
            </p>
            <p className="font-mono">{payload.detected_ts ?? "—"}</p>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-3 sm:grid-cols-2">
        <ClaimCard claim={payload.claim_a} emphasis={aWins ? "winner" : bWins ? "loser" : "neutral"} />
        <ClaimCard claim={payload.claim_b} emphasis={bWins ? "winner" : aWins ? "loser" : "neutral"} />
      </div>

      {payload.system_resolution && (
        <div className="flex items-start gap-2 rounded-md border border-info/40 bg-info/5 p-3 text-sm">
          <Scale className="mt-0.5 size-4 shrink-0 text-info" />
          <div>
            <p className="text-xs font-semibold">
              System resolution:{" "}
              <Badge variant="secondary" className="ml-1 font-mono">
                {payload.system_resolution}
              </Badge>
            </p>
            {payload.resolution_reason && (
              <p className="mt-1 text-xs text-muted-foreground">
                {payload.resolution_reason}
              </p>
            )}
          </div>
        </div>
      )}

      <AuditTrail
        rows={[
          { ts: payload.detected_ts ?? "now", kind: "conflict_detected", detail: "Resolver step 1" },
          ...(payload.system_resolution
            ? [
                {
                  ts: payload.detected_ts ?? "now",
                  kind: `system_resolution:${payload.system_resolution}`,
                  detail: payload.resolution_reason ?? "per FR-6.1",
                },
              ]
            : []),
          { ts: "now", kind: "hitl_pending", detail: "Auto-escalated for human review" },
        ]}
      />
    </div>
  );
}
