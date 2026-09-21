"""OpenAI-compatible providers for `LLMClient`. Confined to `src/gateway/`."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from src.gateway.api import GatewayResponse, strip_json_fences


@dataclass
class OpenAIAdapter:
    """OpenAI-compatible provider. The default config targets OpenAI proper
    (GPT-4.1-mini for ADR-006 3-vendor judge calibration), but the same adapter
    drives xAI Grok, NVIDIA NIM, and Together AI by overriding `base_url` +
    `api_key_env` (all three expose OpenAI-compatible `chat.completions`).
    """

    vendor: str = "openai"
    model: str = "gpt-4.1-mini"
    api_key_env: str = "OPENAI_API_KEY"
    base_url: str | None = None
    pricing_per_million_tokens_in: float = 0.40
    pricing_per_million_tokens_out: float = 1.60
    timeout: float | None = None        # per-request seconds; None = SDK default (no hard cap)
    max_retries: int = 2                # SDK-level auto-retry on transient/timeout
    _client: Any | None = field(default=None, init=False, repr=False)

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI  # noqa: PLC0415 — optional SDK, lazy import by design
        except ImportError as e:  # pragma: no cover
            raise ImportError(
                "OpenAIAdapter requires the `openai` SDK. "
                "Install with `pip install openai`.",
            ) from e
        api_key = os.environ.get(self.api_key_env)
        kwargs: dict[str, Any] = {"max_retries": self.max_retries}
        if api_key:
            kwargs["api_key"] = api_key
        if self.base_url:
            kwargs["base_url"] = self.base_url
        if self.timeout is not None:
            kwargs["timeout"] = self.timeout
        self._client = OpenAI(**kwargs)
        return self._client

    def complete(
        self,
        prompt: str,
        *,
        schema: type[BaseModel] | None = None,
        cache_key: str | None = None,
        cache_ttl: int = 3600,
        temperature: float | None = None,
    ) -> GatewayResponse:
        if cache_ttl != 3600:
            raise ValueError(f"cache_ttl must be 3600 (FR-2.5); got {cache_ttl}")
        client = self._ensure_client()
        start = time.perf_counter()
        # `temperature=0` makes structured tasks (stance derivation, adjudication)
        # reproducible; omitted (None) preserves the model default for everything else.
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        response = client.chat.completions.create(**kwargs)
        latency_ms = (time.perf_counter() - start) * 1000
        text = response.choices[0].message.content or ""
        parsed: Any = text
        if schema is not None:
            try:
                parsed = schema.model_validate(json.loads(strip_json_fences(text)))
            except (json.JSONDecodeError, ValueError):
                parsed = None
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        cost = (
            input_tokens * self.pricing_per_million_tokens_in
            + output_tokens * self.pricing_per_million_tokens_out
        ) / 1_000_000
        _ = cache_key
        return GatewayResponse(
            vendor=self.vendor, model=self.model,
            output=parsed, raw_text=text,
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            cached_input_tokens=0,
            cost_usd=float(cost), latency_ms=float(latency_ms),
            cache_hit=False,
            audit_id=f"audit:{response.id}" if hasattr(response, "id") else "audit:openai",
            ttl_pinned=3600,
        )


def xai_grok_adapter(model: str = "grok-3") -> OpenAIAdapter:
    """xAI Grok via OpenAI-compat endpoint. Default: grok-3 (override per call)."""

    return OpenAIAdapter(
        vendor="xai", model=model,
        api_key_env="XAI_API_KEY",
        base_url="https://api.x.ai/v1",
        pricing_per_million_tokens_in=2.0,
        pricing_per_million_tokens_out=10.0,
    )


def nvidia_nim_adapter(model: str = "meta/llama-3.1-8b-instruct") -> OpenAIAdapter:
    """NVIDIA Build / NIM via OpenAI-compat endpoint. Default: Llama 3.1 8B."""

    return OpenAIAdapter(
        vendor="nvidia", model=model,
        api_key_env="NVIDIA_API_KEY",
        base_url="https://integrate.api.nvidia.com/v1",
        pricing_per_million_tokens_in=0.0,   # NIM build platform = free tier
        pricing_per_million_tokens_out=0.0,
    )


def together_adapter(model: str = "meta-llama/Llama-3.3-70B-Instruct-Turbo") -> OpenAIAdapter:
    """Together AI (open-model fallback) via OpenAI-compat endpoint.
    Default: Llama 3.3 70B (serverless)."""

    return OpenAIAdapter(
        vendor="together", model=model,
        api_key_env="TOGETHER_API_KEY",
        base_url="https://api.together.xyz/v1",
        pricing_per_million_tokens_in=0.88,
        pricing_per_million_tokens_out=0.88,
    )
