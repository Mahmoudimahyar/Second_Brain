/// <reference types="vitest" />
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { WebSearchDisagreementBody } from "./WebSearchDisagreementBody";

describe("WebSearchDisagreementBody", () => {
  it("renders the claim + verdict per signal", () => {
    render(
      <WebSearchDisagreementBody
        claim="NYU dental tuition is approximately $87,000"
        signal_a={{
          label: "tavily_qna",
          verdict: "supports",
          confidence: 0.92,
          evidence_excerpt: "Tuition is around $87,000.",
        }}
        signal_b={{
          label: "tavily_paraphrase_search",
          verdict: "supports",
          confidence: 0.88,
        }}
        signal_c={{
          label: "llm_verify",
          verdict: "disagreement",
          confidence: 0,
          vendor_breakdown: {
            haiku: { verdict: "supports", confidence: 0.95, evidence_excerpt: "" },
            gemini: { verdict: "refutes", confidence: 0.85, evidence_excerpt: "" },
            degraded: false,
          },
        }}
        combine_outcome="disagreement"
        citations={["https://dental.nyu.edu"]}
      />,
    );
    expect(screen.getByText(/NYU dental tuition/)).toBeInTheDocument();
    // Each signal label is rendered as a strong/heading.
    expect(screen.getByText(/Tavily QNA/)).toBeInTheDocument();
    expect(screen.getByText(/Tavily search/)).toBeInTheDocument();
    expect(screen.getByText(/LLM verify/)).toBeInTheDocument();
    // Citation visible.
    expect(screen.getByText(/dental\.nyu\.edu/)).toBeInTheDocument();
  });
});
