"use client";

/**
 * Per-type HITL body for the V1.5c `web_search_disagreement` item type
 * (ADR-016 v2). Renders the three signals (Tavily QNA + Tavily search +
 * two-vendor LLM verify) side-by-side so the reviewer can see exactly
 * why signal C disagreed.
 */

import { Badge } from "@/components/ui/badge";

type Signal = {
  label: string;
  verdict?: string;
  confidence?: number;
  evidence_excerpt?: string;
  vendor_breakdown?: {
    haiku?: { verdict: string; confidence: number; evidence_excerpt: string };
    gemini?: { verdict: string; confidence: number; evidence_excerpt: string };
    degraded?: boolean;
  };
};

interface Props {
  claim: string;
  signal_a?: Signal;
  signal_b?: Signal;
  signal_c?: Signal;
  combine_outcome?: string;
  citations?: string[];
}

const VERDICT_VARIANT: Record<
  string,
  "secondary" | "success" | "destructive" | "warning" | "default"
> = {
  supports: "success",
  refutes: "destructive",
  unknown: "warning",
  disagreement: "warning",
};

function VerdictBadge({ verdict }: { verdict?: string }) {
  const v = verdict?.toLowerCase() ?? "unknown";
  return (
    <Badge variant={VERDICT_VARIANT[v] ?? "default"}>{v}</Badge>
  );
}

function SignalBlock({ label, signal }: { label: string; signal?: Signal }) {
  if (!signal) return null;
  return (
    <div className="rounded border bg-gray-50 p-3 text-sm space-y-1">
      <header className="flex justify-between items-center">
        <strong>{label}</strong>
        <VerdictBadge verdict={signal.verdict} />
      </header>
      {typeof signal.confidence === "number" && (
        <p className="text-xs text-gray-600">
          confidence: {signal.confidence.toFixed(2)}
        </p>
      )}
      {signal.evidence_excerpt && (
        <blockquote className="border-l-2 border-gray-300 pl-2 text-gray-700">
          {signal.evidence_excerpt}
        </blockquote>
      )}
      {signal.vendor_breakdown && (
        <details className="text-xs text-gray-600">
          <summary>Two-vendor breakdown</summary>
          <dl className="mt-1 space-y-1">
            <div>
              <dt className="inline font-medium">Haiku: </dt>
              <dd className="inline">
                {signal.vendor_breakdown.haiku?.verdict}{" "}
                ({signal.vendor_breakdown.haiku?.confidence?.toFixed(2)})
              </dd>
            </div>
            <div>
              <dt className="inline font-medium">Gemini: </dt>
              <dd className="inline">
                {signal.vendor_breakdown.gemini?.verdict}{" "}
                ({signal.vendor_breakdown.gemini?.confidence?.toFixed(2)})
              </dd>
            </div>
            {signal.vendor_breakdown.degraded && (
              <p className="text-yellow-700">
                ⚠ degraded mode — one vendor failed.
              </p>
            )}
          </dl>
        </details>
      )}
    </div>
  );
}

export function WebSearchDisagreementBody({
  claim,
  signal_a,
  signal_b,
  signal_c,
  combine_outcome,
  citations,
}: Props) {
  return (
    <div className="space-y-3">
      <div>
        <p className="text-xs uppercase tracking-wide text-gray-500">Claim</p>
        <p className="font-medium">{claim}</p>
      </div>
      {combine_outcome && (
        <p className="text-sm text-gray-700">
          Combine outcome: <VerdictBadge verdict={combine_outcome} />
        </p>
      )}
      <div className="grid gap-2 md:grid-cols-3">
        <SignalBlock label="Signal A · Tavily QNA" signal={signal_a} />
        <SignalBlock label="Signal B · Tavily search" signal={signal_b} />
        <SignalBlock label="Signal C · LLM verify" signal={signal_c} />
      </div>
      {citations && citations.length > 0 && (
        <div>
          <p className="text-xs uppercase tracking-wide text-gray-500">
            Citations ({citations.length})
          </p>
          <ul className="text-sm space-y-1">
            {citations.slice(0, 5).map((url) => (
              <li key={url} className="truncate">
                <a
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 underline"
                >
                  {url}
                </a>
              </li>
            ))}
            {citations.length > 5 && (
              <li className="text-xs text-gray-500">
                …{citations.length - 5} more.
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
