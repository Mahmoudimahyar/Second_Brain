"""V1.5c BAML templates for web-verification (ADR-016 v2).

Three templates:
- `make_question_from_claim` — turn a disputed graph claim into a question.
- `paraphrase_question` — rephrase a question to differ in ≥ 3 content words.
- `verify_claim_from_evidence` — given evidence excerpts, support/refute/unknown.

Each template ships as a Python callable that routes through the model
gateway. The BAML `.baml` file (when BAML is wired) becomes the
authoritative prompt spec; the Python wrappers below are the runtime
entry points.
"""
