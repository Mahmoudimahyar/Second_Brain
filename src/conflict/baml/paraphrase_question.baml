// V1.5c — BAML template (ADR-016 v2 step 3).
//
// Rephrase a question to differ in ≥ 3 content words OR change phrasing
// structure. Produces signal B's input.
//
// Routed by `src.conflict.baml.templates.paraphrase_via_gateway` to
// gateway TaskID.WEB_VERIFY_PARAPHRASE. Primary = Gemini 2.5 Flash-Lite,
// fallback = Haiku 4.5 (per docs/04-architecture/tech-stack.md line 79).
//
// Purpose: avoid signal A and signal B being near-duplicates of the same
// Tavily index lookup (the "1.5-signal" failure mode flagged in the
// V1.5 gap audit CRITICAL-2).

class ParaphraseInput {
  question string @description("The original question (signal A's query).")
}

class ParaphraseOutput {
  paraphrased string @description("A rephrased question with ≥ 3 content-word changes.")
}

function ParaphraseQuestion(input: ParaphraseInput) -> ParaphraseOutput {
  client GeminiFlashLite
  prompt #"
    Rephrase the following question to mean the same thing but use
    substantially different wording. Requirements:
      - Change at least 3 content words (nouns / verbs / adjectives).
      - Keep the question type (yes/no, factual, comparison) identical.
      - Preserve all named entities (school names, program names, dates,
        dollar amounts, percentages) exactly.
      - Do NOT add new claims or assumptions.
      - One question only.

    Original question:
    {{ input.question }}

    Return ONLY the paraphrased question. No prefix, no quotes, no markdown.
  "#
}
