"use client";

/**
 * Per-type HITL body for the V1.5c `tavily_unavailable` item type
 * (ADR-016 v2 §10). Shows the failed verify run + remediation hints.
 */

import { Badge } from "@/components/ui/badge";

interface Props {
  claim: string;
  error: string;
  attempts?: number;
  last_attempt_at?: string;
}

export function TavilyUnavailableBody({
  claim,
  error,
  attempts,
  last_attempt_at,
}: Props) {
  return (
    <div className="space-y-3">
      <div>
        <p className="text-xs uppercase tracking-wide text-gray-500">Claim</p>
        <p className="font-medium">{claim}</p>
      </div>
      <div>
        <Badge variant="destructive">tavily_unavailable</Badge>{" "}
        {attempts !== undefined && (
          <span className="text-xs text-gray-500 ml-2">
            {attempts} attempt{attempts === 1 ? "" : "s"}
            {last_attempt_at ? ` · last ${last_attempt_at}` : ""}
          </span>
        )}
      </div>
      <pre className="rounded bg-red-50 border border-red-200 px-3 py-2 text-xs whitespace-pre-wrap text-red-900 font-mono">
        {error}
      </pre>
      <details className="text-sm">
        <summary>Suggested next steps</summary>
        <ul className="list-disc ml-5 mt-1 text-gray-700 space-y-1">
          <li>Verify <code>TAVILY_API_KEY</code> is set + not over quota.</li>
          <li>
            Check the Tavily status page; if green, click "Retry" to re-attempt
            the verify run.
          </li>
          <li>
            If Tavily is persistently down, the claim falls back to V1's
            three-vendor LLM judge (per ADR-006). Accept and the resolver
            will route through that path on the next sweep.
          </li>
        </ul>
      </details>
    </div>
  );
}
