from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from typing import Any, Protocol

from pydantic import BaseModel

from src.shared.timestamps import utc_now


class TaskID(StrEnum):
    """Per-task selection criteria per ADR-011 + R-009 + tech-stack matrix.

    The ``WEB_VERIFY_*`` and ``TEAM_CONTENT_ANGLES`` slots are V1.5c
    additions per ADR-016 v2 and the per-task matrix in
    ``docs/04-architecture/tech-stack.md``.
    """

    PASS3_CLUSTER_SUMMARY = "pass3.cluster_summary"
    PASS4_SENTIMENT = "pass4.sentiment"
    PASS4_INTERVIEW_Q = "pass4.interview_q"
    PASS4_CONFLICT_CANDIDATE = "pass4.conflict_candidate"
    PASS4_HARDEST = "pass4.hardest"
    JUDGE_TIE_BREAK = "judge.tie_break"
    HITL_SUMMARY = "hitl.summary"
    # ADR-022 — LLM-matcher fallback for the low-confidence ER band
    ENTITY_MATCH_HARD = "er.entity_match_hard"
    # V1.5c — web-verification (ADR-016 v2)
    WEB_VERIFY_MAKE_QUESTION = "web_verify.make_question_from_claim"
    WEB_VERIFY_PARAPHRASE = "web_verify.paraphrase_question"
    WEB_VERIFY_CLAIM_HAIKU = "web_verify.verify_claim_from_evidence.haiku"
    WEB_VERIFY_CLAIM_GEMINI = "web_verify.verify_claim_from_evidence.gemini"
    # V1.5c — per-team angle suggestions (model-swappable per V1.5-R2)
    TEAM_CONTENT_ANGLES = "team_content_angles"


@dataclass(frozen=True)
class GatewayResponse:
    vendor: str
    model: str
    output: Any                       # parsed schema instance if a schema was given
    raw_text: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    cost_usd: float
    latency_ms: float
    cache_hit: bool
    audit_id: str
    ttl_pinned: int = 3600           # NON-NEGOTIABLE per FR-2.5 / GAP-031


class LLMClient(Protocol):
    """Vendor-portable interface every concrete provider implements.

    All vendor-specific code is contained in `src/gateway/<vendor>_adapter.py`.
    The rest of the engine programs against `LLMClient` + `GatewayResponse`.
    """

    vendor: str
    model: str

    def complete(
        self,
        prompt: str,
        *,
        schema: type[BaseModel] | None = None,
        cache_key: str | None = None,
        cache_ttl: int = 3600,
    ) -> GatewayResponse: ...


@dataclass(frozen=True)
class MockProvider:
    """Test / dev provider. Returns deterministic stubs without any network call.

    Useful for unit tests + offline development. Production providers
    (`AnthropicAdapter`, `OpenAIAdapter`, `GeminiAdapter`) plug in via the
    `LLMClient` Protocol when API keys are available.
    """

    vendor: str = "mock"
    model: str = "mock-v1"
    cost_per_call_usd: float = 0.0
    fixture: Callable[[str], str] | None = None

    def complete(
        self,
        prompt: str,
        *,
        schema: type[BaseModel] | None = None,
        cache_key: str | None = None,
        cache_ttl: int = 3600,
    ) -> GatewayResponse:
        _ = cache_key  # interface parity; mock provider does not cache
        if cache_ttl != 3600:
            raise ValueError(
                f"cache_ttl must be 3600 (FR-2.5); got {cache_ttl}",
            )
        if self.fixture is not None:
            text = self.fixture(prompt)
        else:
            text = f"mock-response[{self.vendor}:{self.model}]: {prompt[:32]}"
        parsed: Any = text
        if schema is not None:
            try:
                parsed = schema.model_validate(json.loads(text))
            except (json.JSONDecodeError, ValueError):
                # tests can supply a fixture that returns valid JSON for schema'd calls;
                # if not, fall back to default-constructed schema.
                parsed = None
        return GatewayResponse(
            vendor=self.vendor,
            model=self.model,
            output=parsed,
            raw_text=text,
            input_tokens=len(prompt.split()),
            output_tokens=len(text.split()),
            cached_input_tokens=0,
            cost_usd=self.cost_per_call_usd,
            latency_ms=0.0,
            cache_hit=False,
            audit_id=_audit_id(prompt, self.vendor, self.model),
            ttl_pinned=cache_ttl,
        )


@dataclass
class FallbackClient:
    """Runtime circuit-breaker. Tries `primary` first; on any exception, tries `fallback`.

    Closes GAP-046 for the live case: when Anthropic returns a non-recoverable
    runtime error (credit exhausted, 5xx, rate-limit hard-fail), the same
    request lands on the secondary provider instead of dying.

    Design:
      - `vendor` / `model` reflect the **configured primary** so logs report
        the intended routing. The actual provider used per call is visible on
        `GatewayResponse.vendor`.
      - V1 catches every Exception (broad). V1.x can narrow to specific
        SDK exception types or add an exponential-backoff retry on the
        primary before falling through.
    """

    primary: LLMClient
    fallback: LLMClient
    vendor: str = field(init=False)
    model: str = field(init=False)

    def __post_init__(self) -> None:
        self.vendor = self.primary.vendor
        self.model = self.primary.model

    def complete(
        self,
        prompt: str,
        *,
        schema: type[BaseModel] | None = None,
        cache_key: str | None = None,
        cache_ttl: int = 3600,
    ) -> GatewayResponse:
        try:
            return self.primary.complete(
                prompt, schema=schema, cache_key=cache_key, cache_ttl=cache_ttl,
            )
        except Exception:
            return self.fallback.complete(
                prompt, schema=schema, cache_key=cache_key, cache_ttl=cache_ttl,
            )


@dataclass
class ModelGateway:
    """Routes per-task → vendor model per ADR-011.

    V1 routing is configured via `task_to_client`. A V1.x extension would
    add LiteLLM as a unified router; for V1 we keep it explicit.
    """

    task_to_client: dict[TaskID, LLMClient] = field(default_factory=dict)
    default_client: LLMClient | None = None

    def complete(
        self,
        task: TaskID,
        prompt: str,
        *,
        schema: type[BaseModel] | None = None,
        cache_key: str | None = None,
        cache_ttl: int = 3600,
    ) -> GatewayResponse:
        client = self.task_to_client.get(task, self.default_client)
        if client is None:
            raise RuntimeError(
                f"No provider configured for task {task.value} and no default set",
            )
        return client.complete(
            prompt, schema=schema, cache_key=cache_key, cache_ttl=cache_ttl,
        )

    def register(self, task: TaskID, client: LLMClient) -> None:
        self.task_to_client[task] = client


def _wire_extraction_models(
    gw: ModelGateway,
    *,
    have_gemini: bool,
    have_anthropic: bool,
    have_openai: bool,
) -> tuple[LLMClient | None, LLMClient | None, LLMClient | None, LLMClient | None]:
    """Construct + register the Pass-3/4 + judge clients (ADR-003 matrix, refreshed
    2026-05-30). Returns (flash_lite, gemini_flash, haiku, sonnet) for the
    web-verify + cascade slots.

    Model IDs are **env-overridable** (`SECBRAIN_MODEL_*`) with defaults verified
    against vendor docs on 2026-05-30 but NOT runtime-pinged here (no live spend)
    — confirm each with one live call before a full-corpus run. A bad OpenAI id
    degrades to the Anthropic model via `FallbackClient`, so a wrong id costs the
    saving, not the run. Rationale + prices:
    `.agent/reports/v1.7-model-routing-research-2026-05-30.md`.
    """
    import os  # noqa: PLC0415 — env-driven init

    # Lazy imports avoid circular dep (adapters import GatewayResponse from this module).
    from src.gateway.anthropic_adapter import AnthropicAdapter  # noqa: PLC0415
    from src.gateway.gemini_adapter import GeminiAdapter  # noqa: PLC0415
    from src.gateway.openai_adapter import OpenAIAdapter  # noqa: PLC0415

    def _mid(key: str, default: str) -> str:
        return os.environ.get(key, default)

    cheap_id = _mid("SECBRAIN_MODEL_CHEAP", "gemini-2.5-flash-lite")          # $0.10/$0.40 (cheapest GA)
    gem_flash_id = _mid("SECBRAIN_MODEL_GEMINI_FLASH", "gemini-2.5-flash")    # $0.30/$2.50
    interview_id = _mid("SECBRAIN_MODEL_INTERVIEW", "gpt-5-mini")             # $0.125/$1.00
    conflict_id = _mid("SECBRAIN_MODEL_CONFLICT", "claude-haiku-4-5-20251001")  # $1/$5 (precision; A/B pending)
    hardest_id = _mid("SECBRAIN_MODEL_HARDEST", "gpt-5.4")                    # $2.50/$15 (reasoning leader)
    sonnet_id = _mid("SECBRAIN_MODEL_SONNET", "claude-sonnet-4-6")            # cascade final tier
    fallback_id = _mid("SECBRAIN_MODEL_FALLBACK", "gpt-5-mini")               # was gpt-4.1-mini (superseded)

    flash_lite: LLMClient | None = None
    gemini_flash: LLMClient | None = None
    if have_gemini:
        flash_lite = GeminiAdapter(model=cheap_id)
        gemini_flash = GeminiAdapter(model=gem_flash_id)
        gw.register(TaskID.PASS3_CLUSTER_SUMMARY, flash_lite)
        gw.register(TaskID.PASS4_SENTIMENT, flash_lite)
        gw.register(TaskID.HITL_SUMMARY, flash_lite)

    # OpenAI mid/premium adapters (prices set for accurate cost telemetry).
    openai_interview = OpenAIAdapter(
        model=interview_id, pricing_per_million_tokens_in=0.125,
        pricing_per_million_tokens_out=1.00) if have_openai else None
    openai_fallback = OpenAIAdapter(
        model=fallback_id, pricing_per_million_tokens_in=0.125,
        pricing_per_million_tokens_out=1.00) if have_openai else None
    openai_hardest = OpenAIAdapter(
        model=hardest_id, pricing_per_million_tokens_in=2.50,
        pricing_per_million_tokens_out=15.0) if have_openai else None

    haiku: LLMClient | None = None
    sonnet: LLMClient | None = None
    if have_anthropic:
        haiku = AnthropicAdapter(model=conflict_id)
        sonnet = AnthropicAdapter(model=sonnet_id)

    # Per-task routing: interview-Q + hardest lead with the cheaper/stronger
    # OpenAI model; conflict-candidate stays Anthropic-primary (JSON-stable,
    # precision — flip to gpt-5-mini only after the on-data A/B). Each degrades
    # cross-vendor to whatever key is present (GAP-046).
    interview_client = _pick_with_fallback(openai_interview, haiku)
    conflict_client = _pick_with_fallback(haiku, openai_fallback)
    hardest_client = _pick_with_fallback(openai_hardest, sonnet)
    judge_client = haiku if haiku is not None else openai_fallback

    if interview_client is not None:
        gw.register(TaskID.PASS4_INTERVIEW_Q, interview_client)
    if conflict_client is not None:
        gw.register(TaskID.PASS4_CONFLICT_CANDIDATE, conflict_client)
    if hardest_client is not None:
        gw.register(TaskID.PASS4_HARDEST, hardest_client)
    if judge_client is not None:
        gw.register(TaskID.JUDGE_TIE_BREAK, judge_client)

    # Plan B (benchmark-won routing; opt-in via SECBRAIN_PLAN_B). sentiment +
    # interview_q -> Gemini Flash with the v2 rubric prompts; conflict_candidate
    # -> Together Llama-3.3-70B (best claim recall + JSON-stable on a short prompt).
    # Rationale + measured leaderboard: cloud/bench/.
    if os.environ.get("SECBRAIN_PLAN_B"):
        from src.gateway.openai_adapter import (  # noqa: PLC0415
            OpenAIAdapter, nvidia_nim_adapter, together_adapter)
        variant = os.environ.get("SECBRAIN_PLANB_VARIANT", "gemini")
        if variant == "grok":
            # No-Gemini path (Gemini free-tier 10k/day cap blocks scale): sentiment +
            # interview_q -> xAI grok-3-mini (0.950 blend); conflict -> gpt-5-nano (0.56
            # recall). Both paid, no daily request cap. Benchmark: cloud/bench/.
            grok = OpenAIAdapter(
                vendor="xai", model="grok-3-mini", api_key_env="XAI_API_KEY",
                base_url="https://api.x.ai/v1",
                pricing_per_million_tokens_in=0.30, pricing_per_million_tokens_out=0.50)
            nano = OpenAIAdapter(
                model="gpt-5-nano", pricing_per_million_tokens_in=0.05,
                pricing_per_million_tokens_out=0.40)
            gw.register(TaskID.PASS4_SENTIMENT, grok)
            gw.register(TaskID.PASS4_INTERVIEW_Q, grok)
            gw.register(TaskID.PASS4_CONFLICT_CANDIDATE, nano)
        elif variant == "llama":
            # All-Together path (best available: conflict 0.78 — the champion).
            llama = together_adapter(_mid("SECBRAIN_MODEL_CONFLICT_LLAMA",
                                          "meta-llama/Llama-3.3-70B-Instruct-Turbo"))
            gw.register(TaskID.PASS4_SENTIMENT, llama)
            gw.register(TaskID.PASS4_INTERVIEW_Q, llama)
            gw.register(TaskID.PASS4_CONFLICT_CANDIDATE, llama)
        elif variant == "nim":
            # FREE NVIDIA NIM (same Llama-3.3-70B). Watch for free-tier throttling.
            nim = nvidia_nim_adapter("meta/llama-3.3-70b-instruct")
            gw.register(TaskID.PASS4_SENTIMENT, nim)
            gw.register(TaskID.PASS4_INTERVIEW_Q, nim)
            gw.register(TaskID.PASS4_CONFLICT_CANDIDATE, nim)
        elif variant == "oss":
            # Together open-source serverless (benchmark-won 2026-06-07; cloud/bench/).
            # Bulk sentiment+interview -> cheap OSS model; conflict -> optionally a
            # stronger OSS model. Model IDs + per-Mtok pricing are env-driven so we can
            # switch models without code edits AND keep cost telemetry accurate
            # (default together_adapter hardcodes $0.88, which would mis-bill OSS).
            def _tg2(mkey, mdef, pinkey, poutkey, dpin, dpout):
                return OpenAIAdapter(
                    vendor="together", model=_mid(mkey, mdef),
                    api_key_env="TOGETHER_API_KEY",
                    base_url="https://api.together.xyz/v1",
                    pricing_per_million_tokens_in=float(os.environ.get(pinkey, dpin)),
                    pricing_per_million_tokens_out=float(os.environ.get(poutkey, dpout)),
                    timeout=float(os.environ.get("SECBRAIN_TG_TIMEOUT", "90")),
                    max_retries=2)
            _bulk_id = _mid("SECBRAIN_TG_MODEL", "openai/gpt-oss-20b")
            bulk = _tg2("SECBRAIN_TG_MODEL", "openai/gpt-oss-20b",
                        "SECBRAIN_TG_PIN", "SECBRAIN_TG_POUT", 0.05, 0.20)
            conflict = _tg2("SECBRAIN_TG_CONFLICT_MODEL", _bulk_id,
                            "SECBRAIN_TG_CPIN", "SECBRAIN_TG_CPOUT", 0.05, 0.20)
            gw.register(TaskID.PASS4_SENTIMENT, bulk)
            gw.register(TaskID.PASS4_INTERVIEW_Q, bulk)
            gw.register(TaskID.PASS4_CONFLICT_CANDIDATE, conflict)
            # Pass-3 cluster summaries -> same cap-free OSS model (Gemini is still
            # free-tier capped; a summary failure mid-run would waste the ~3h embed).
            gw.register(TaskID.PASS3_CLUSTER_SUMMARY, bulk)
        else:
            if gemini_flash is not None:
                gw.register(TaskID.PASS4_SENTIMENT, gemini_flash)
                gw.register(TaskID.PASS4_INTERVIEW_Q, gemini_flash)
            provider = os.environ.get("SECBRAIN_CONFLICT_PROVIDER", "together")
            if provider == "together" and os.environ.get("TOGETHER_API_KEY"):
                llama_id = _mid("SECBRAIN_MODEL_CONFLICT_LLAMA",
                                "meta-llama/Llama-3.3-70B-Instruct-Turbo")
                gw.register(TaskID.PASS4_CONFLICT_CANDIDATE, together_adapter(llama_id))
            elif flash_lite is not None:
                gw.register(TaskID.PASS4_CONFLICT_CANDIDATE, flash_lite)

    return flash_lite, gemini_flash, haiku, sonnet


def default_gateway() -> ModelGateway:
    """Build a fully-configured `ModelGateway` (ADR-003 per-task matrix, refreshed
    2026-05-30 — see `_wire_extraction_models` + the model-routing research report).

    Provider selection is driven by which API keys are present in env:
      - Pass 3 cluster summary / Pass 4 sentiment / HITL summary → Gemini Flash-Lite
      - Pass 4 interview-Q  → GPT-5 mini   (fallback Haiku 4.5)
      - Pass 4 conflict cand. → Haiku 4.5  (Anthropic-primary; fallback GPT-5 mini)
      - Pass 4 hardest cases → GPT-5.4     (fallback Sonnet 4.6)
      - Judge tie-break      → ADR-006 3-vendor panel lives outside this function;
                               the gateway registers a primary (Haiku) here.

    All model IDs are env-overridable (`SECBRAIN_MODEL_*`). Missing keys fall
    through silently — those tasks raise `RuntimeError` if invoked. GAP-046:
    when only one vendor key is present it fills all the slots so Pass 4 keeps
    running.
    """

    import os  # noqa: PLC0415 — env-driven init

    gw = ModelGateway()
    have_gemini = bool(
        os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"),
    )
    have_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
    have_openai = bool(os.environ.get("OPENAI_API_KEY"))

    flash_lite, gemini_flash, haiku, sonnet = _wire_extraction_models(
        gw, have_gemini=have_gemini, have_anthropic=have_anthropic,
        have_openai=have_openai,
    )

    # ------------------------------------------------------------------
    # V1.5c — web-verification + team-content-angles slots per tech-stack
    # matrix lines 78-81. Primary = Gemini Flash-Lite; fallback = Haiku 4.5
    # for the question/paraphrase/angles tasks. Verify-claim runs two
    # vendors in parallel via the W1-2 wrapper; both slots are registered
    # independently here so the wrapper can dispatch to each.
    # ------------------------------------------------------------------

    web_verify_question_client = _pick_with_fallback(flash_lite, haiku)
    if web_verify_question_client is not None:
        gw.register(TaskID.WEB_VERIFY_MAKE_QUESTION, web_verify_question_client)
        gw.register(TaskID.WEB_VERIFY_PARAPHRASE, web_verify_question_client)
        gw.register(TaskID.TEAM_CONTENT_ANGLES, web_verify_question_client)
        # ADR-022 LLM-matcher fallback — cheap tier first (Flash-Lite → Haiku).
        gw.register(TaskID.ENTITY_MATCH_HARD, web_verify_question_client)

    # Verify-claim Haiku vendor (no fallback to Gemini here — the W1-2
    # wrapper handles single-vendor degraded mode if a vendor 5xx's).
    if haiku is not None:
        gw.register(TaskID.WEB_VERIFY_CLAIM_HAIKU, haiku)

    # Verify-claim Gemini vendor — use the standard Gemini Flash (not
    # Flash-Lite) because the spec is "Haiku + Gemini Flash" in tech-stack
    # matrix line 80.
    if gemini_flash is not None:
        gw.register(TaskID.WEB_VERIFY_CLAIM_GEMINI, gemini_flash)

    # ADR-023 — calibrated cascade. Default OFF (set SECBRAIN_CASCADE=1 to enable):
    # routes the Pass-4 conflict/interview tasks through a Haiku→Sonnet cascade
    # that escalates only when calibrated confidence < 0.7. Until a labeled trace
    # set exists the calibrator is identity + router off, so behavior == today's
    # task-matrix routing on confident items (cost-regression safe).
    if os.environ.get("SECBRAIN_CASCADE") and haiku is not None and sonnet is not None:
        from src.gateway.routing import CalibratedCascade, CascadeTier  # noqa: PLC0415

        cascade = CalibratedCascade(tiers=[
            CascadeTier(client=haiku, min_confidence=0.7),
            CascadeTier(client=sonnet, min_confidence=0.0),  # final tier
        ])
        gw.register(TaskID.PASS4_CONFLICT_CANDIDATE, cascade)
        gw.register(TaskID.PASS4_INTERVIEW_Q, cascade)

    return gw


def _pick_with_fallback(
    primary: LLMClient | None,
    fallback: LLMClient | None,
) -> LLMClient | None:
    """Return ``primary`` if present; if both, wrap with ``FallbackClient``.

    Used by ``default_gateway()`` for V1.5c slots where the spec allows a
    cross-vendor fallback (e.g., Gemini primary → Haiku fallback per
    tech-stack matrix lines 78-79, 81).
    """

    if primary is None:
        return fallback
    if fallback is None:
        return primary
    return FallbackClient(primary=primary, fallback=fallback)


def strip_json_fences(text: str) -> str:
    """Strip ```json ... ``` markdown fences so inner JSON parses.

    Vendors (notably Gemini, sometimes Anthropic/OpenAI when asked for JSON)
    wrap structured output in code fences. Handles:
      - ```json\\n{...}\\n```
      - ```\\n{...}\\n```
      - leading prose then ```json...``` (drops the prose)
      - bare {...} or [...]
    """

    s = text.strip()
    if not s:
        return s
    fence_open = s.find("```")
    if fence_open == -1:
        return s
    # Skip the opening fence + any language tag on the same line.
    after_tag = s.find("\n", fence_open + 3)
    after_tag = after_tag + 1 if after_tag != -1 else fence_open + 3
    fence_close = s.find("```", after_tag)
    if fence_close != -1:
        return s[after_tag:fence_close].strip()
    return s[after_tag:].strip()


def _audit_id(prompt: str, vendor: str, model: str) -> str:
    h = sha256()
    h.update(prompt.encode("utf-8"))
    h.update(b"|")
    h.update(vendor.encode("ascii"))
    h.update(b"|")
    h.update(model.encode("ascii"))
    h.update(b"|")
    h.update(utc_now().isoformat().encode("ascii"))
    return f"audit:{h.hexdigest()[:16]}"
