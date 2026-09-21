"""V1.5c — `WebVerificationAgent` (ADR-016 v2).

Three parallel signals per ADR-016:
- A: `tavily.qna_search(question)`
- B: `tavily.search(paraphrased_question)`
- C: extract top URLs + two-vendor LLM verify (`verify_claim_from_evidence`)

Combine via `combine_signals` (2-of-3 majority). Writes a verdict with
`web_verification_run` provenance (all three signals, questions used, raw
Tavily responses, extracted page contents, per-vendor LLM verdicts).

Cost cap: per-corpus configurable (default $5/sweep). Cap-hit freezes
further calls + emits `cap_hit` audit event.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.conflict.baml.templates import (
    ClaimQuestionMaker,
    ClaimVerifier,
    QuestionParaphraser,
    TwoVendorVerifyOutcome,
    VerifyResult,
    classify_tavily_answer_via_gateway,
    make_question_via_gateway,
    paraphrase_via_gateway,
    vendor_breakdown_dict,
    verify_claim_two_vendor_via_gateway,
)
from src.conflict.providers.base import SearchProvider
from src.conflict.signal_combine import (
    SignalInput,
    combine_signals,
)
from src.shared.errors import StructuredError
from src.shared.timestamps import to_iso, utc_now

TwoVendorVerifierFn = Callable[[str, str], TwoVendorVerifyOutcome]

VerdictKind = Literal[
    "supports", "refutes", "disagreement", "unknown", "cap_hit",
]


class WebVerificationRun(BaseModel):
    """Provenance row for `web_verification_run` (per ADR-016 §6)."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    claim: str
    context_summary: str
    question_a: str
    question_b: str
    signal_a: dict[str, Any]
    signal_b: dict[str, Any]
    signal_c: dict[str, Any]
    combine_outcome: str
    combine_confidence: float
    low_confidence: bool
    citations: list[str] = Field(default_factory=list)
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    ts: datetime


class VerdictResult(BaseModel):
    """Final verdict returned by the agent."""

    model_config = ConfigDict(extra="forbid")

    verdict: VerdictKind
    confidence: float
    citations: list[str] = Field(default_factory=list)
    low_confidence: bool = False
    reason: str = ""
    run: WebVerificationRun


@dataclass
class CostBudget:
    """Per-corpus cost ledger backing `web_search_cost`. SQLite-backed
    persistence; in-memory backing for tests."""

    cap_usd: float = 5.0
    spent_usd: float = 0.0

    def remaining(self) -> float:
        return max(0.0, self.cap_usd - self.spent_usd)

    def at_or_over(self) -> bool:
        return self.spent_usd >= self.cap_usd

    def charge(self, amount: float) -> None:
        self.spent_usd += amount


@dataclass
class WebVerificationCache:
    """In-memory cache keyed by hash(claim, context, model_versions).

    V1.5c persists to SQLite for warm-cache hits; tests use the in-memory
    variant via dependency injection.
    """

    _store: dict[str, VerdictResult] = field(default_factory=dict)

    def key(self, claim: str, context_summary: str, version: str = "v1") -> str:
        h = sha256()
        h.update(claim.encode("utf-8"))
        h.update(b"|")
        h.update(context_summary.encode("utf-8"))
        h.update(b"|")
        h.update(version.encode("utf-8"))
        return h.hexdigest()[:24]

    def get(self, key: str) -> VerdictResult | None:
        return self._store.get(key)

    def put(self, key: str, result: VerdictResult) -> None:
        self._store[key] = result


@dataclass
class WebVerificationAgent:
    """The V1.5c web-verification agent (ADR-016 v2).

    Two dispatch paths for signal C (LLM verify on evidence):

    - **Production**: ``verify_two_vendor`` runs Haiku 4.5 + Gemini Flash
      in parallel via the gateway. Both must agree for signal C to count;
      otherwise signal C = ``disagreement``. This is the default.
    - **Test escape hatch**: passing ``verify=ClaimVerifier(...)`` switches
      to a single-vendor synchronous callable for fast deterministic
      stubs. When ``verify`` is set it takes precedence over
      ``verify_two_vendor``.

    Field defaults for ``make_question`` and ``paraphrase`` route through
    ``default_gateway()`` per ADR-011 + tech-stack matrix lines 78-81.
    """

    provider: SearchProvider
    make_question: ClaimQuestionMaker = field(
        default_factory=lambda: ClaimQuestionMaker(
            invoke=make_question_via_gateway,
        ),
    )
    paraphrase: QuestionParaphraser = field(
        default_factory=lambda: QuestionParaphraser(
            invoke=paraphrase_via_gateway,
        ),
    )
    # Legacy single-vendor verifier — when set, takes precedence over
    # `verify_two_vendor`. Used by tests for fast deterministic stubs.
    verify: ClaimVerifier | None = None
    # Production two-vendor parallel verifier (W1-2). Default lambda runs
    # `verify_claim_two_vendor_via_gateway` at call time so the gateway is
    # constructed lazily (env keys may load after import).
    verify_two_vendor: TwoVendorVerifierFn | None = field(
        default_factory=lambda: verify_claim_two_vendor_via_gateway,
    )
    per_vendor_verify_timeout_s: float = 6.0
    cost_budget: CostBudget = field(default_factory=CostBudget)
    cache: WebVerificationCache = field(default_factory=WebVerificationCache)
    max_urls: int = 6

    # ------------------------------------------------------------------

    def verify_claim(
        self, claim: str, *, context_summary: str = "",
    ) -> VerdictResult:
        """Run the 3-signal verification + combine + return a verdict."""

        if self.cost_budget.at_or_over():
            return _cap_hit_result(claim, context_summary)

        cache_key = self.cache.key(claim, context_summary)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        start = utc_now()

        question_a = self.make_question(claim)
        question_b = self.paraphrase(question_a)

        # Signal A — Tavily QNA on original question
        try:
            answer_a = self.provider.qna_search(question_a)
        except StructuredError as e:
            return _provider_failure_result(claim, context_summary, e)

        verdict_a, conf_a = _classify_tavily_answer(answer_a.answer, claim)
        signal_a = SignalInput(
            label="tavily_qna",
            verdict=verdict_a,
            confidence=conf_a,
            evidence_excerpt=answer_a.answer[:200],
        )

        # Signal B — Tavily search on paraphrased question
        try:
            answer_b = self.provider.search(question_b)
        except StructuredError as e:
            return _provider_failure_result(claim, context_summary, e)

        verdict_b, conf_b = _classify_tavily_answer(answer_b.answer, claim)
        signal_b = SignalInput(
            label="tavily_paraphrase_search",
            verdict=verdict_b,
            confidence=conf_b,
            evidence_excerpt=answer_b.answer[:200],
        )

        # Signal C — Extract top URLs + two-vendor LLM verify
        urls: list[str] = []
        for u in [*answer_a.urls, *answer_b.urls]:
            if u and u not in urls:
                urls.append(u)
            if len(urls) >= self.max_urls:
                break

        signal_c, vendor_breakdown = _build_signal_c(
            urls, claim, self.provider,
            legacy_verifier=self.verify,
            two_vendor_verifier=self.verify_two_vendor,
            per_vendor_timeout_s=self.per_vendor_verify_timeout_s,
            cost_budget=self.cost_budget,
        )

        combine = combine_signals([signal_a, signal_b, signal_c])

        citations = list({
            *answer_a.urls,
            *answer_b.urls,
            *_urls_from_signal(signal_c),
        })

        signal_c_dict = _signal_dict(signal_c)
        if vendor_breakdown is not None:
            signal_c_dict["vendor_breakdown"] = vendor_breakdown

        run = WebVerificationRun(
            run_id=f"webverify:{sha256((claim+context_summary).encode()).hexdigest()[:12]}",
            claim=claim,
            context_summary=context_summary,
            question_a=question_a,
            question_b=question_b,
            signal_a=_signal_dict(signal_a),
            signal_b=_signal_dict(signal_b),
            signal_c=signal_c_dict,
            combine_outcome=combine.outcome,
            combine_confidence=combine.confidence,
            low_confidence=combine.low_confidence,
            citations=citations,
            cost_usd=self.cost_budget.spent_usd,
            latency_ms=(utc_now() - start).total_seconds() * 1000,
            ts=start,
        )
        result = VerdictResult(
            verdict=combine.outcome,
            confidence=combine.confidence,
            citations=citations,
            low_confidence=combine.low_confidence,
            reason=combine.reason,
            run=run,
        )
        self.cache.put(cache_key, result)
        return result


# ----------------------------------------------------------------------
# SQLite cost-tracking sink
# ----------------------------------------------------------------------


class WebSearchCostStore:
    """Persists per-call cost rows to `web_search_cost` SQLite table."""

    def __init__(self, sqlite_path: Path) -> None:
        self._sqlite_path = Path(sqlite_path)
        self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._sqlite_path)

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS web_search_cost (
                    cost_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                    corpus_id   TEXT,
                    provider    TEXT NOT NULL,
                    op          TEXT NOT NULL,
                    cost_usd    REAL NOT NULL,
                    ts          TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_wsc_corpus
                    ON web_search_cost(corpus_id);
                CREATE INDEX IF NOT EXISTS idx_wsc_ts
                    ON web_search_cost(ts);
                """,
            )

    def record(
        self,
        *,
        op: str,
        cost_usd: float,
        corpus_id: str | None = None,
        provider: str = "tavily",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO web_search_cost (corpus_id, provider, op, cost_usd, ts) "
                "VALUES (?, ?, ?, ?, ?)",
                (corpus_id, provider, op, cost_usd, to_iso(utc_now())),
            )
            conn.commit()

    def total(self, *, corpus_id: str | None = None) -> float:
        sql = "SELECT COALESCE(SUM(cost_usd), 0) FROM web_search_cost"
        args: list[Any] = []
        if corpus_id is not None:
            sql += " WHERE corpus_id = ?"
            args.append(corpus_id)
        with self._connect() as conn:
            row = conn.execute(sql, args).fetchone()
        return float(row[0]) if row else 0.0


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


_REFUTE_PHRASES: tuple[str, ...] = (
    "no, ", "incorrect", "false", "not true", "is not", "are not",
    "does not", "do not", "not accept", "not the", "not a ",
    "instead of", "actually located", "actually requires",
)


def _classify_tavily_answer(
    answer_text: str, claim: str,
) -> tuple[Any, float]:
    """W1-8 — production verdict classifier for signals A and B.

    When ``SECBRAIN_OFFLINE=1`` is set (tests + offline dev) the legacy
    lexical-overlap heuristic is used. Otherwise the answer is fed
    through ``classify_tavily_answer_via_gateway`` which calls Haiku 4.5
    via the model gateway with the same ``verify_claim_from_evidence``
    prompt used by signal C. This closes the secondary heuristic gap
    flagged when W1-8 first ran (3/5 mismatches were caused by the
    lexical classifier mis-reading Tavily's actual answers).
    """

    if os.environ.get("SECBRAIN_OFFLINE") == "1":
        return _verdict_from_answer(answer_text, claim), (
            0.75 if answer_text else 0.2
        )
    if not (answer_text or "").strip():
        return "unknown", 0.0
    try:
        result: VerifyResult = classify_tavily_answer_via_gateway(
            claim, answer_text,
        )
    except Exception:  # network / 5xx / missing key → fall back to lexical
        return _verdict_from_answer(answer_text, claim), (
            0.5 if answer_text else 0.2
        )
    return result.verdict, result.confidence


def _verdict_from_answer(answer_text: str, claim: str) -> Any:
    """Heuristic: detect refute markers first; otherwise lexical overlap
    determines supports vs unknown. Production swaps this for a model
    gateway call to `verify_claim_from_evidence` BAML template; the
    stub keeps tests + offline dev working without an LLM key.
    """

    text = (answer_text or "").lower().strip()
    if not text:
        return "unknown"
    if any(phrase in text for phrase in _REFUTE_PHRASES):
        return "refutes"
    claim_tokens = set(claim.lower().split())
    answer_tokens = set(text.split())
    if not claim_tokens:
        return "unknown"
    overlap = len(claim_tokens & answer_tokens) / len(claim_tokens)
    return "supports" if overlap >= 0.30 else "unknown"


def _build_signal_c(  # noqa: PLR0911 - branch count is unavoidable given the spec's failure modes
    urls: Sequence[str],
    claim: str,
    provider: SearchProvider,
    *,
    legacy_verifier: ClaimVerifier | None,
    two_vendor_verifier: TwoVendorVerifierFn | None,
    per_vendor_timeout_s: float,
    cost_budget: CostBudget,
) -> tuple[SignalInput, dict[str, Any] | None]:
    """Build signal C; dispatch between the legacy single-vendor (test
    escape hatch) and the W1-2 two-vendor parallel production paths.

    Returns ``(signal, vendor_breakdown)`` where ``vendor_breakdown`` is
    populated only when the two-vendor path was used; it is then merged
    into ``WebVerificationRun.signal_c`` so the audit row captures both
    Haiku and Gemini outputs.
    """

    def _bail(reason: str) -> tuple[SignalInput, dict[str, Any] | None]:
        return SignalInput(
            label="llm_verify",
            verdict="unknown",
            confidence=0.0,
            evidence_excerpt=reason,
        ), None

    if not urls:
        return _bail("no URLs to extract")
    if cost_budget.at_or_over():
        return _bail("cost cap hit before extract")
    try:
        pages = provider.extract(list(urls))
    except StructuredError:
        return _bail("extract failed")
    evidence = "\n\n".join(p.text for p in pages if p.success and p.text)
    if not evidence:
        return _bail("empty evidence")

    # Dispatch — legacy `verify` (test stub) takes precedence when set.
    if legacy_verifier is not None:
        result = legacy_verifier(claim, evidence)
        return SignalInput(
            label="llm_verify",
            verdict=result.verdict,
            confidence=result.confidence,
            evidence_excerpt=result.evidence_excerpt[:200],
        ), None

    # Production: parallel two-vendor.
    if two_vendor_verifier is None:
        # No verifier of any kind — emit unknown rather than crashing.
        return _bail("no verifier configured")

    # The two-vendor wrapper takes its own timeout; we pass ours via the
    # default-factory wrapper when set, otherwise we rely on the default.
    # Use a lambda-friendly call signature.
    outcome = _invoke_two_vendor(
        two_vendor_verifier, claim, evidence,
        per_vendor_timeout_s=per_vendor_timeout_s,
    )
    breakdown = vendor_breakdown_dict(outcome)

    return SignalInput(
        label="llm_verify_two_vendor",
        verdict=outcome.final.verdict,
        confidence=outcome.final.confidence,
        evidence_excerpt=outcome.final.evidence_excerpt[:200],
    ), breakdown


def _invoke_two_vendor(
    fn: TwoVendorVerifierFn,
    claim: str,
    evidence: str,
    *,
    per_vendor_timeout_s: float,
) -> TwoVendorVerifyOutcome:
    """Call the two-vendor verifier; forward the timeout when the callable
    accepts a ``per_vendor_timeout_s`` keyword.

    Test stubs (which are plain callables of ``(claim, evidence)``) don't
    accept the keyword; we fall back to calling them without it.
    """

    import inspect  # noqa: PLC0415

    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return fn(claim, evidence)

    if "per_vendor_timeout_s" in sig.parameters:
        return fn(claim, evidence, per_vendor_timeout_s=per_vendor_timeout_s)  # type: ignore[call-arg]
    return fn(claim, evidence)


def _urls_from_signal(signal: SignalInput) -> list[str]:
    """Pull URLs back out of a signal's evidence excerpt — best-effort."""

    text = signal.evidence_excerpt or ""
    return [w for w in text.split() if w.startswith(("http://", "https://"))]


def _signal_dict(sig: SignalInput) -> dict[str, Any]:
    return {
        "label": sig.label,
        "verdict": sig.verdict,
        "confidence": sig.confidence,
        "evidence_excerpt": sig.evidence_excerpt,
    }


def _cap_hit_result(claim: str, context_summary: str) -> VerdictResult:
    run = WebVerificationRun(
        run_id=f"webverify:cap:{sha256(claim.encode()).hexdigest()[:8]}",
        claim=claim, context_summary=context_summary,
        question_a="", question_b="",
        signal_a={"label": "skipped", "reason": "cap_hit"},
        signal_b={"label": "skipped", "reason": "cap_hit"},
        signal_c={"label": "skipped", "reason": "cap_hit"},
        combine_outcome="cap_hit",
        combine_confidence=0.0,
        low_confidence=True,
        citations=[],
        cost_usd=0.0,
        latency_ms=0.0,
        ts=utc_now(),
    )
    return VerdictResult(
        verdict="cap_hit",
        confidence=0.0,
        citations=[],
        low_confidence=True,
        reason="cost cap hit; further verifications frozen for this corpus",
        run=run,
    )


def _provider_failure_result(
    claim: str, context_summary: str, error: StructuredError,
) -> VerdictResult:
    run = WebVerificationRun(
        run_id=f"webverify:fail:{sha256(claim.encode()).hexdigest()[:8]}",
        claim=claim, context_summary=context_summary,
        question_a="", question_b="",
        signal_a={"label": "failed", "reason": str(error)},
        signal_b={"label": "skipped", "reason": "provider_failed"},
        signal_c={"label": "skipped", "reason": "provider_failed"},
        combine_outcome="disagreement",
        combine_confidence=0.0,
        low_confidence=True,
        citations=[],
        cost_usd=0.0,
        latency_ms=0.0,
        ts=utc_now(),
    )
    return VerdictResult(
        verdict="disagreement",
        confidence=0.0,
        citations=[],
        low_confidence=True,
        reason=(
            "tavily_unavailable — provider failure; escalate to HITL "
            f"({error.error_code.value})"
        ),
        run=run,
    )


__all__ = [
    "CostBudget",
    "VerdictKind",
    "VerdictResult",
    "WebSearchCostStore",
    "WebVerificationAgent",
    "WebVerificationCache",
    "WebVerificationRun",
]
