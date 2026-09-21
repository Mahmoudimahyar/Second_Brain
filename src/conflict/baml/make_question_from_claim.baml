// V1.5c — BAML template (ADR-016 v2 step 2).
//
// Turn a disputed graph claim into a question suitable for Tavily
// `qna_search`. The output is signal A's input.
//
// Routed by `src.conflict.baml.templates.make_question_via_gateway` to
// gateway TaskID.WEB_VERIFY_MAKE_QUESTION. Primary = Gemini 2.5 Flash-Lite,
// fallback = Haiku 4.5 (per docs/04-architecture/tech-stack.md line 78).
//
// The Python-side wrapper inlines this prompt body verbatim until the
// BAML toolchain itself is wired (V1.6); the file remains the authoritative
// prompt spec for review + diffing.

class MakeQuestionInput {
  claim string @description("The disputed factual claim to turn into a question.")
}

class MakeQuestionOutput {
  question string @description("A direct, answerable question on the claim.")
}

function MakeQuestionFromClaim(input: MakeQuestionInput) -> MakeQuestionOutput {
  client GeminiFlashLite
  prompt #"
    You convert disputed factual claims into single, direct questions
    suitable for a web-search QNA API. The question must be answerable
    yes/no or with a short factual phrase. Do not editorialize.
    Do not return more than one question. Do not include reasoning.

    Disputed claim:
    {{ input.claim }}

    Return ONLY the question text. No prefix, no quotes, no markdown.
  "#
}
