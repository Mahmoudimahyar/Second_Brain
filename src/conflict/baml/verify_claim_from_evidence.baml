// V1.5c — BAML template (ADR-016 v2 step 4).
//
// Given a claim + evidence excerpts, return supports / refutes / unknown
// + a confidence + a short evidence excerpt. Runs twice in parallel — once
// against Haiku 4.5, once against Gemini Flash — and signal C only counts
// when both vendors return the same verdict.
//
// Routed by `src.conflict.baml.templates.verify_claim_via_gateway` to
// either TaskID.WEB_VERIFY_CLAIM_HAIKU or TaskID.WEB_VERIFY_CLAIM_GEMINI
// (per docs/04-architecture/tech-stack.md line 80 — "two-vendor parallel,
// both required").

enum Verdict {
  supports
  refutes
  unknown
}

class VerifyClaimInput {
  claim string
  evidence string
}

class VerifyClaimOutput {
  verdict Verdict
  evidence_excerpt string @description("Up to 200 chars from the evidence supporting the verdict.")
  confidence float @description("0.0–1.0 calibrated to the evidence's strength.")
}

function VerifyClaimFromEvidence(input: VerifyClaimInput) -> VerifyClaimOutput {
  // Routed twice in parallel — once to HaikuFourFive, once to GeminiFlash —
  // per ADR-016 v2 §3 step 4. Both verdicts must agree for signal C to
  // count; otherwise signal C = "disagreement".
  prompt #"
    You verify a factual claim against the provided evidence.

    Output exactly one JSON object with these fields:
      - verdict: one of "supports", "refutes", "unknown".
        * "supports" — evidence directly or strongly implies the claim is true.
        * "refutes" — evidence directly or strongly implies the claim is false.
        * "unknown" — evidence is insufficient, off-topic, or ambiguous.
      - evidence_excerpt: up to 200 characters from the evidence that
        most directly supports the verdict.
      - confidence: a float in [0.0, 1.0] reflecting how strongly the
        evidence supports the verdict.

    Strict rules:
      - Do NOT use outside knowledge. Only the evidence below.
      - If the evidence does not address the claim, return "unknown" with
        confidence ≤ 0.3.
      - Do NOT include any text outside the JSON object.
      - Do NOT wrap the JSON in code fences.

    Claim:
    {{ input.claim }}

    Evidence:
    {{ input.evidence }}
  "#
}
