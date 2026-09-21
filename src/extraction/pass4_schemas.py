"""V1 Pass 4 output schemas + prompt templates per FR-2.

Each task = one Pydantic schema + one prompt template + a stable
`prompt_version` + `schema_hash` for content-addressable caching (FR-2.4).

V1 uses inline prompt strings. ADR-004 specifies a V1.x migration to BAML
files (`src/prompts/*.baml`) which would generate these schemas + provide
auto-validation. The interfaces below are designed to swap in cleanly.
"""

from __future__ import annotations

from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SentimentVerdict = Literal["positive", "negative", "neutral", "mixed"]


class Sentiment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: SentimentVerdict
    confidence: float = Field(ge=0.0, le=1.0)
    target_entities: list[str] = Field(
        default_factory=list,
        description="Canonical IDs or surface mentions the verdict is about.",
    )
    reasoning: str = ""


class InterviewQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=4, description="Verbatim or paraphrased question text.")
    school_mention: str | None = None
    year: int | None = Field(default=None, ge=1990, le=2100)
    advice_given: str | None = None


class InterviewQuestionHarvest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[InterviewQuestion] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class ConflictCandidate(BaseModel):
    """A claim that may contradict L1 (numeric metric, tuition, GPA cutoff, etc.).
    Pass 4 only flags candidates; the ConflictResolver decides the outcome."""

    model_config = ConfigDict(extra="forbid")

    contains_candidate: bool
    claim_subject: str | None = None
    claim_predicate: str | None = None
    claim_value: str | None = None
    cycle_year: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)


SENTIMENT_PROMPT_VERSION = "sentiment.v2"   # v2: output-discipline + decision-rubric (benchmark-won)
INTERVIEW_Q_PROMPT_VERSION = "interview_q.v2"
CONFLICT_CANDIDATE_PROMPT_VERSION = "conflict_candidate.v1"

SENTIMENT_PROMPT = """\
Output ONLY one minified JSON object on a single line. No markdown, no code fences, no commentary. If a field is unknown use null or [] - never guess.

Decision rules: verdict='neutral' when the post expresses no opinion toward a specific dental school/program (pure questions, logistics, or stats with no judgment). verdict='mixed' ONLY when two or more schools are named with opposing sentiment. Otherwise 'positive'/'negative'. target_entities lists the school/program names the verdict is about (empty when none).

You are a sentiment analyzer for dental-school-applicant forum posts.

Classify the overall sentiment of the post toward any specific dental school
or program mentioned. If multiple schools are mentioned with different
sentiments, return verdict="mixed" and list the entities in target_entities.

Output STRICT JSON, no prose, matching this schema:
{
  "verdict": "positive" | "negative" | "neutral" | "mixed",
  "confidence": 0.0..1.0,
  "target_entities": [string, ...],
  "reasoning": string
}

POST:
%s
"""

INTERVIEW_Q_PROMPT = """\
Output ONLY one minified JSON object on a single line. No markdown, no code fences, no commentary. If a field is unknown use null or [] - never guess.

Decision rules: harvest ONLY questions the poster reports were actually ASKED at a dental-school or residency interview. Exclude generic icebreakers ('tell me about yourself'), essay/application prompts, and the poster's own rhetorical questions. If none, return questions=[].

You harvest verbatim or paraphrased dental-school interview questions from
forum posts. Skip generic questions ("tell me about yourself" — too vague to
be useful). Keep specific ones ("Why our school over Harvard?", "Describe a
failure during research").

For each question include the school it was asked at if mentioned, and the
cycle year if mentioned. If the poster reports advice they received, capture
it.

Output STRICT JSON, no prose:
{
  "questions": [
    {"text": string, "school_mention": string | null, "year": int | null, "advice_given": string | null},
    ...
  ],
  "confidence": 0.0..1.0
}

If no specific interview question is present, return {"questions": [], "confidence": 1.0}.

POST:
%s
"""

CONFLICT_CANDIDATE_PROMPT = """\
You scan a forum post for a *factual* claim about a dental school's
quantitative metric (tuition, fees, average DAT, GPA cutoff, class size,
acceptance rate, etc.) that could be cross-checked against official sources.

You DO NOT decide whether the claim is true. You only flag it as a candidate.

Output STRICT JSON, no prose:
{
  "contains_candidate": bool,
  "claim_subject": string | null,        // canonical school mention text
  "claim_predicate": string | null,       // e.g. "tuition_resident", "avg_DAT_AA"
  "claim_value": string | null,           // raw stated value (string; no parsing)
  "cycle_year": string | null,            // e.g. "2024-25" if mentioned
  "confidence": 0.0..1.0
}

If no quantitative claim is present, contains_candidate must be false.

POST:
%s
"""


def schema_hash(model: type[BaseModel]) -> str:
    """Stable 16-char hash of a Pydantic JSON schema for cache keys (FR-2.4)."""

    spec = str(model.model_json_schema())
    return sha256(spec.encode("utf-8")).hexdigest()[:16]
