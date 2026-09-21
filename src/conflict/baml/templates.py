"""V1.5c BAML template Python wrappers (ADR-016 v2).

Two layers:

- Production: ``make_question_via_gateway``, ``paraphrase_via_gateway``,
  ``verify_claim_via_gateway``. Each routes through ``default_gateway()``
  using the TaskID slots registered per ``docs/04-architecture/tech-stack.md``
  lines 78-81. The authoritative prompt bodies live in the sibling ``.baml``
  files (``make_question_from_claim.baml`` / ``paraphrase_question.baml`` /
  ``verify_claim_from_evidence.baml``); the inlined Python prompts below
  duplicate those bodies verbatim until the BAML toolchain itself is wired
  (V1.6).

- Offline fallback: ``heuristic_make_question``, ``heuristic_paraphrase``,
  ``heuristic_verify_claim``. Trivial deterministic stubs for tests and
  offline dev. **Each raises ``RuntimeError`` unless ``SECBRAIN_OFFLINE=1``
  is set in the environment** — this is the runtime gate that prevents
  the prior session's failure mode of shipping the heuristic Python as
  the production code path (gap-audit CRITICAL-1 + CRITICAL-2).

The ``ClaimQuestionMaker`` / ``QuestionParaphraser`` / ``ClaimVerifier``
dataclasses remain the dependency-injection surface for
``WebVerificationAgent``; the agent's field defaults now wire the
gateway-routed production callables.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from src.gateway.api import ModelGateway, TaskID, default_gateway

# ----------------------------------------------------------------------
# Types
# ----------------------------------------------------------------------


Verdict = Literal["supports", "refutes", "unknown", "disagreement"]


class VerifyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Verdict
    evidence_excerpt: str
    confidence: float


@dataclass
class ClaimQuestionMaker:
    """``make_question_from_claim`` — turn a disputed claim into a question."""

    invoke: Callable[[str], str]

    def __call__(self, claim: str) -> str:
        return self.invoke(claim)


@dataclass
class QuestionParaphraser:
    """``paraphrase_question`` — rephrase to differ in ≥ 3 content words."""

    invoke: Callable[[str], str]

    def __call__(self, question: str) -> str:
        return self.invoke(question)


@dataclass
class ClaimVerifier:
    """``verify_claim_from_evidence`` — supports / refutes / unknown."""

    invoke: Callable[[str, str], VerifyResult]

    def __call__(self, claim: str, evidence: str) -> VerifyResult:
        return self.invoke(claim, evidence)


# ----------------------------------------------------------------------
# Production — gateway-routed (ADR-016 v2 + tech-stack matrix)
# ----------------------------------------------------------------------


_MAKE_QUESTION_PROMPT = (
    "You convert disputed factual claims into single, direct questions "
    "suitable for a web-search QNA API. The question must be answerable "
    "yes/no or with a short factual phrase. Do not editorialize. "
    "Do not return more than one question. Do not include reasoning.\n\n"
    "Disputed claim:\n{claim}\n\n"
    "Return ONLY the question text. No prefix, no quotes, no markdown."
)


_PARAPHRASE_PROMPT = (
    "Rephrase the following question to mean the same thing but use "
    "substantially different wording. Requirements:\n"
    "  - Change at least 3 content words (nouns / verbs / adjectives).\n"
    "  - Keep the question type (yes/no, factual, comparison) identical.\n"
    "  - Preserve all named entities (school names, program names, dates, "
    "dollar amounts, percentages) exactly.\n"
    "  - Do NOT add new claims or assumptions.\n"
    "  - One question only.\n\n"
    "Original question:\n{question}\n\n"
    "Return ONLY the paraphrased question. No prefix, no quotes, no markdown."
)


_VERIFY_CLAIM_PROMPT = (
    "You verify a factual claim against the provided evidence.\n\n"
    "Output exactly one JSON object with these fields:\n"
    '  - verdict: one of "supports", "refutes", "unknown".\n'
    '    * "supports" — evidence directly or strongly implies the claim is true.\n'
    '    * "refutes" — evidence directly or strongly implies the claim is false.\n'
    '    * "unknown" — evidence is insufficient, off-topic, or ambiguous.\n'
    "  - evidence_excerpt: up to 200 characters from the evidence that "
    "most directly supports the verdict.\n"
    "  - confidence: a float in [0.0, 1.0] reflecting how strongly the "
    "evidence supports the verdict.\n\n"
    "Strict rules:\n"
    "  - Do NOT use outside knowledge. Only the evidence below.\n"
    "  - If the evidence does not address the claim, return \"unknown\" with "
    "confidence ≤ 0.3.\n"
    "  - Do NOT include any text outside the JSON object.\n"
    "  - Do NOT wrap the JSON in code fences.\n\n"
    "Claim:\n{claim}\n\n"
    "Evidence:\n{evidence}"
)


def _resolve_gateway(gateway: ModelGateway | None) -> ModelGateway:
    return gateway if gateway is not None else default_gateway()


def make_question_via_gateway(
    claim: str,
    *,
    gateway: ModelGateway | None = None,
) -> str:
    """Production path for ``make_question_from_claim``.

    Routes through ``TaskID.WEB_VERIFY_MAKE_QUESTION`` (Gemini 2.5 Flash-Lite
    primary, Haiku 4.5 fallback per tech-stack matrix line 78).
    """

    gw = _resolve_gateway(gateway)
    prompt = _MAKE_QUESTION_PROMPT.format(claim=claim)
    response = gw.complete(TaskID.WEB_VERIFY_MAKE_QUESTION, prompt)
    return _normalize_question(response.raw_text)


def paraphrase_via_gateway(
    question: str,
    *,
    gateway: ModelGateway | None = None,
) -> str:
    """Production path for ``paraphrase_question``.

    Routes through ``TaskID.WEB_VERIFY_PARAPHRASE`` (Gemini 2.5 Flash-Lite
    primary, Haiku 4.5 fallback per tech-stack matrix line 79).
    """

    gw = _resolve_gateway(gateway)
    prompt = _PARAPHRASE_PROMPT.format(question=question)
    response = gw.complete(TaskID.WEB_VERIFY_PARAPHRASE, prompt)
    return _normalize_question(response.raw_text)


@dataclass(frozen=True)
class VendorVerifyResult:
    """One vendor's raw output from ``verify_claim_from_evidence``.

    The W1-2 two-vendor wrapper preserves both vendors' verdicts +
    latencies + errors in this struct so the
    ``WebVerificationRun.signal_c`` audit row can record both sides.
    """

    vendor: str
    verdict: Verdict
    evidence_excerpt: str
    confidence: float
    latency_ms: float
    error: str | None = None


@dataclass(frozen=True)
class TwoVendorVerifyOutcome:
    """Reconciled output of a parallel two-vendor verify run (ADR-016 v2 §3 step 4).

    Both vendors run in parallel via a thread pool with per-vendor timeout.
    Reconciliation rules:
      - Both succeed AND agree → ``final.verdict`` = the agreed verdict,
        confidence = mean(haiku, gemini), ``degraded=False``.
      - Both succeed AND disagree → ``final.verdict`` = ``"disagreement"``,
        confidence = 0.0, ``degraded=False``.
      - Exactly one succeeds → ``final.verdict`` = surviving vendor's verdict,
        confidence = surviving / 2 (halved for low-confidence flag),
        ``degraded=True``.
      - Both fail → ``final.verdict`` = ``"unknown"``, confidence = 0.0,
        ``degraded=False``.
    """

    final: VerifyResult
    haiku: VendorVerifyResult
    gemini: VendorVerifyResult
    degraded: bool


def verify_claim_via_gateway(
    *,
    claim: str,
    evidence: str,
    task: TaskID,
    gateway: ModelGateway | None = None,
) -> VerifyResult:
    """Production path for ``verify_claim_from_evidence``.

    Caller picks the vendor via ``task`` (one of
    ``WEB_VERIFY_CLAIM_HAIKU`` or ``WEB_VERIFY_CLAIM_GEMINI``). The W1-2
    wrapper runs both in parallel and reconciles.
    """

    if task not in {
        TaskID.WEB_VERIFY_CLAIM_HAIKU,
        TaskID.WEB_VERIFY_CLAIM_GEMINI,
    }:
        raise ValueError(
            f"verify_claim_via_gateway requires a verify-claim TaskID; "
            f"got {task!r}",
        )

    gw = _resolve_gateway(gateway)
    prompt = _VERIFY_CLAIM_PROMPT.format(claim=claim, evidence=evidence)
    response = gw.complete(task, prompt)
    return _parse_verify_response(response.raw_text, evidence=evidence)


def _normalize_question(text: str) -> str:
    """Strip whitespace, quotes, and a leading code-fence if the model added one."""

    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        # Drop a single leading fence + optional language tag.
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        cleaned = cleaned.rstrip("`").strip()
    if cleaned.startswith(("\"", "'")) and cleaned.endswith(("\"", "'")):
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _parse_verify_response(raw_text: str, *, evidence: str) -> VerifyResult:
    """Parse a JSON verify response; degrade to ``unknown`` on malformed output."""

    from src.gateway.api import strip_json_fences  # noqa: PLC0415 — local

    cleaned = strip_json_fences(raw_text or "")
    try:
        payload = json.loads(cleaned)
        verdict_raw = str(payload.get("verdict", "unknown")).lower()
        verdict: Verdict
        if verdict_raw == "supports":
            verdict = "supports"
        elif verdict_raw == "refutes":
            verdict = "refutes"
        else:
            verdict = "unknown"
        excerpt = str(payload.get("evidence_excerpt", ""))[:200]
        confidence = float(payload.get("confidence", 0.0))
    except (json.JSONDecodeError, ValueError, TypeError):
        return VerifyResult(
            verdict="unknown",
            evidence_excerpt=evidence[:200],
            confidence=0.0,
        )

    return VerifyResult(
        verdict=verdict,
        evidence_excerpt=excerpt or evidence[:200],
        confidence=max(0.0, min(1.0, confidence)),
    )


# ----------------------------------------------------------------------
# W1-2 — Two-vendor parallel verify (ADR-016 v2 §3 step 4)
# ----------------------------------------------------------------------


_DEFAULT_PER_VENDOR_TIMEOUT_S: float = 6.0


def _verify_one_vendor(
    *,
    claim: str,
    evidence: str,
    task: TaskID,
    vendor_label: str,
    gateway: ModelGateway,
) -> VendorVerifyResult:
    """Single-vendor verify call wrapper that catches exceptions and
    captures latency. Used by the two-vendor parallel wrapper."""

    start = time.perf_counter()
    try:
        result = verify_claim_via_gateway(
            claim=claim, evidence=evidence, task=task, gateway=gateway,
        )
    except Exception as exc:  # capture everything as vendor failure
        return VendorVerifyResult(
            vendor=vendor_label,
            verdict="unknown",
            evidence_excerpt="",
            confidence=0.0,
            latency_ms=(time.perf_counter() - start) * 1000.0,
            error=f"{type(exc).__name__}: {exc}",
        )
    return VendorVerifyResult(
        vendor=vendor_label,
        verdict=result.verdict,
        evidence_excerpt=result.evidence_excerpt,
        confidence=result.confidence,
        latency_ms=(time.perf_counter() - start) * 1000.0,
        error=None,
    )


def verify_claim_two_vendor_via_gateway(
    claim: str,
    evidence: str,
    *,
    gateway: ModelGateway | None = None,
    per_vendor_timeout_s: float = _DEFAULT_PER_VENDOR_TIMEOUT_S,
) -> TwoVendorVerifyOutcome:
    """W1-2 production verifier — runs Haiku 4.5 + Gemini Flash in parallel.

    Per ADR-016 v2 §3 step 4: both vendors run in parallel; both must
    agree for signal C to count, otherwise signal C = ``disagreement``.
    Per-vendor timeout from ADR-016 v2 §9 (default 6s).

    The two vendor calls go through a ``ThreadPoolExecutor`` because the
    gateway adapters are synchronous; the wait is I/O-bound so threads
    are sufficient.
    """

    gw = _resolve_gateway(gateway)

    with ThreadPoolExecutor(max_workers=2) as executor:
        haiku_future = executor.submit(
            _verify_one_vendor,
            claim=claim, evidence=evidence,
            task=TaskID.WEB_VERIFY_CLAIM_HAIKU,
            vendor_label="haiku", gateway=gw,
        )
        gemini_future = executor.submit(
            _verify_one_vendor,
            claim=claim, evidence=evidence,
            task=TaskID.WEB_VERIFY_CLAIM_GEMINI,
            vendor_label="gemini", gateway=gw,
        )

        # Wait up to per_vendor_timeout_s for both; record timeout as
        # vendor failure for any that hasn't finished.
        wait(
            [haiku_future, gemini_future],
            timeout=per_vendor_timeout_s,
            return_when=FIRST_COMPLETED,
        )
        # Give the slower one a bit more grace (up to the same budget),
        # so a slightly-slow second vendor still lands.
        wait(
            [haiku_future, gemini_future],
            timeout=per_vendor_timeout_s,
        )

        haiku = _harvest_future(haiku_future, "haiku")
        gemini = _harvest_future(gemini_future, "gemini")

    return _reconcile_two_vendor(haiku=haiku, gemini=gemini, evidence=evidence)


def _harvest_future(future: Any, vendor_label: str) -> VendorVerifyResult:
    """Pull the VendorVerifyResult from a future; mark as timeout if not done."""

    from concurrent.futures import Future  # noqa: PLC0415

    assert isinstance(future, Future)
    if not future.done():
        future.cancel()
        return VendorVerifyResult(
            vendor=vendor_label,
            verdict="unknown",
            evidence_excerpt="",
            confidence=0.0,
            latency_ms=0.0,
            error="TimeoutError: vendor exceeded per_vendor_timeout_s",
        )
    try:
        result: VendorVerifyResult = future.result(timeout=0)
        return result
    except Exception as exc:  # final harvesting catches all
        return VendorVerifyResult(
            vendor=vendor_label,
            verdict="unknown",
            evidence_excerpt="",
            confidence=0.0,
            latency_ms=0.0,
            error=f"{type(exc).__name__}: {exc}",
        )


def _reconcile_two_vendor(
    *,
    haiku: VendorVerifyResult,
    gemini: VendorVerifyResult,
    evidence: str,
) -> TwoVendorVerifyOutcome:
    haiku_ok = haiku.error is None
    gemini_ok = gemini.error is None

    if not haiku_ok and not gemini_ok:
        # Both failed → unknown.
        final = VerifyResult(
            verdict="unknown",
            evidence_excerpt=evidence[:200],
            confidence=0.0,
        )
        return TwoVendorVerifyOutcome(
            final=final, haiku=haiku, gemini=gemini, degraded=False,
        )

    if haiku_ok != gemini_ok:
        # Exactly one returned → degraded mode (halve confidence).
        sole = haiku if haiku_ok else gemini
        final = VerifyResult(
            verdict=sole.verdict,
            evidence_excerpt=sole.evidence_excerpt or evidence[:200],
            confidence=sole.confidence * 0.5,
        )
        return TwoVendorVerifyOutcome(
            final=final, haiku=haiku, gemini=gemini, degraded=True,
        )

    # Both succeeded.
    if haiku.verdict != gemini.verdict:
        # Disagreement → signal C cannot count per ADR-016 v2.
        final = VerifyResult(
            verdict="disagreement",
            evidence_excerpt=(
                f"haiku={haiku.verdict}/{haiku.confidence:.2f}; "
                f"gemini={gemini.verdict}/{gemini.confidence:.2f}"
            )[:200],
            confidence=0.0,
        )
        return TwoVendorVerifyOutcome(
            final=final, haiku=haiku, gemini=gemini, degraded=False,
        )

    # Both agree.
    avg_conf = (haiku.confidence + gemini.confidence) / 2.0
    # Prefer the longer excerpt as the canonical evidence string.
    excerpt = (
        haiku.evidence_excerpt
        if len(haiku.evidence_excerpt) >= len(gemini.evidence_excerpt)
        else gemini.evidence_excerpt
    )
    final = VerifyResult(
        verdict=haiku.verdict,
        evidence_excerpt=excerpt[:200],
        confidence=avg_conf,
    )
    return TwoVendorVerifyOutcome(
        final=final, haiku=haiku, gemini=gemini, degraded=False,
    )


def classify_tavily_answer_via_gateway(
    claim: str,
    tavily_answer: str,
    *,
    gateway: ModelGateway | None = None,
) -> VerifyResult:
    """W1-8 — production verdict classifier for signals A + B.

    Signals A and B feed Tavily's synthesized answer back through the
    same verify-claim BAML template (Haiku 4.5 single-vendor; signal C
    is the two-vendor variant). This closes the secondary heuristic gap
    flagged in W1-8: ``web_verify._verdict_from_answer`` was a
    lexical-overlap heuristic that bypassed the gateway and gave wrong
    verdicts on claims like "DAT has 5 sections" when Tavily said "4".

    Returns a ``VerifyResult`` with verdict ∈ {``supports``, ``refutes``,
    ``unknown``}, classified by the LLM on (claim, tavily_answer).
    """

    return verify_claim_via_gateway(
        claim=claim,
        evidence=tavily_answer,
        task=TaskID.WEB_VERIFY_CLAIM_HAIKU,
        gateway=gateway,
    )


def vendor_breakdown_dict(outcome: TwoVendorVerifyOutcome) -> dict[str, Any]:
    """Serialize a ``TwoVendorVerifyOutcome`` for ``WebVerificationRun.signal_c``."""

    return {
        "haiku": {
            "verdict": outcome.haiku.verdict,
            "confidence": outcome.haiku.confidence,
            "evidence_excerpt": outcome.haiku.evidence_excerpt,
            "latency_ms": outcome.haiku.latency_ms,
            "error": outcome.haiku.error,
        },
        "gemini": {
            "verdict": outcome.gemini.verdict,
            "confidence": outcome.gemini.confidence,
            "evidence_excerpt": outcome.gemini.evidence_excerpt,
            "latency_ms": outcome.gemini.latency_ms,
            "error": outcome.gemini.error,
        },
        "degraded": outcome.degraded,
    }


# ----------------------------------------------------------------------
# Offline fallbacks — gated on SECBRAIN_OFFLINE=1
# ----------------------------------------------------------------------


_OFFLINE_ENV = "SECBRAIN_OFFLINE"
_OFFLINE_GUARD_MSG = (
    "Production code path invoked the offline heuristic ({fn}). "
    f"Set {_OFFLINE_ENV}=1 for tests, or wire the real dependency. "
    "See gap audit CRITICAL-1 + CRITICAL-2."
)


def _assert_offline_mode(fn_name: str) -> None:
    if os.environ.get(_OFFLINE_ENV) != "1":
        raise RuntimeError(_OFFLINE_GUARD_MSG.format(fn=fn_name))


def heuristic_make_question(claim: str) -> str:
    """Offline-mode stub. Raises unless ``SECBRAIN_OFFLINE=1``.

    Trivial claim→question converter. Tests opt in via the autouse
    fixture in ``tests/conflict/conftest.py``; production uses
    ``make_question_via_gateway``.
    """

    _assert_offline_mode("heuristic_make_question")
    cleaned = claim.strip().rstrip(".?!")
    if cleaned.lower().startswith(("is ", "are ", "was ", "were ", "does ", "did ", "do ")):
        return f"{cleaned}?"
    return f"Is the following claim accurate: {cleaned}?"


def heuristic_paraphrase(question: str) -> str:
    """Offline-mode stub. Raises unless ``SECBRAIN_OFFLINE=1``."""

    _assert_offline_mode("heuristic_paraphrase")
    q = question.strip()
    swaps = [
        ("What is", "Which is"),
        ("How much", "How many"),
        ("Is the following claim accurate", "Can the following claim be verified"),
        ("Was", "Were"),
    ]
    for src, dst in swaps:
        if src in q:
            return q.replace(src, dst, 1)
    return f"Specifically, {q}"


def heuristic_verify_claim(claim: str, evidence: str) -> VerifyResult:
    """Offline-mode stub. Raises unless ``SECBRAIN_OFFLINE=1``.

    Trivial lexical-overlap verifier. Tests use this to avoid an LLM
    round-trip; production routes through the gateway via
    ``verify_claim_via_gateway``.
    """

    _assert_offline_mode("heuristic_verify_claim")
    claim_tokens = set(claim.lower().split())
    evidence_tokens = set(evidence.lower().split())
    if not claim_tokens:
        return VerifyResult(verdict="unknown", evidence_excerpt="", confidence=0.0)
    overlap = len(claim_tokens & evidence_tokens) / len(claim_tokens)
    if overlap < 0.30:
        return VerifyResult(
            verdict="unknown",
            evidence_excerpt=evidence[:200],
            confidence=overlap,
        )
    return VerifyResult(
        verdict="supports",
        evidence_excerpt=evidence[:200],
        confidence=min(overlap, 0.95),
    )


__all__ = [
    "ClaimQuestionMaker",
    "ClaimVerifier",
    "QuestionParaphraser",
    "TwoVendorVerifyOutcome",
    "VendorVerifyResult",
    "Verdict",
    "VerifyResult",
    "classify_tavily_answer_via_gateway",
    "heuristic_make_question",
    "heuristic_paraphrase",
    "heuristic_verify_claim",
    "make_question_via_gateway",
    "paraphrase_via_gateway",
    "vendor_breakdown_dict",
    "verify_claim_two_vendor_via_gateway",
    "verify_claim_via_gateway",
]
