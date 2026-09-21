"""Anthropic provider for `LLMClient`. Confined to `src/gateway/` per the
vendor-SDK-ban in `dependency-rules.md` / non-negotiable #9.

Production install: `pip install anthropic`. The SDK is imported lazily so
unit tests run without the dependency.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from src.gateway.api import GatewayResponse, strip_json_fences


@dataclass
class AnthropicAdapter:
    """Vendor-portable wrapper over the Anthropic Messages API.

    Pinned to prompt cache `ttl=3600` per FR-2.5 / GAP-031. Per ADR-011 the
    default model is Claude Haiku 4.5 (batch-friendly for Pass 4); Sonnet 4.6
    is used for the hardest ~2% of cases (per the per-task matrix in
    `memory/project_dentistjourney.md`).
    """

    vendor: str = "anthropic"
    model: str = "claude-haiku-4-5-20251001"
    api_key_env: str = "ANTHROPIC_API_KEY"
    system_prompt: str = ""
    max_tokens: int = 1024
    pricing_per_million_tokens_in: float = 1.0      # placeholder; pulled from Anthropic pricing
    pricing_per_million_tokens_out: float = 5.0
    _client: Any | None = field(default=None, init=False, repr=False)

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import anthropic  # noqa: PLC0415 — optional SDK, lazy import by design
        except ImportError as e:  # pragma: no cover
            raise ImportError(
                "AnthropicAdapter requires the `anthropic` SDK. "
                "Install with `pip install anthropic`.",
            ) from e
        self._client = anthropic.Anthropic()
        return self._client

    def complete(
        self,
        prompt: str,
        *,
        schema: type[BaseModel] | None = None,
        cache_key: str | None = None,
        cache_ttl: int = 3600,
    ) -> GatewayResponse:
        if cache_ttl != 3600:
            raise ValueError(f"cache_ttl must be 3600 (FR-2.5); got {cache_ttl}")
        client = self._ensure_client()
        start = time.perf_counter()
        call_kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if self.system_prompt:
            call_kwargs["system"] = [{
                "type": "text", "text": self.system_prompt,
                "cache_control": {"type": "ephemeral", "ttl": "1h"},
            }]
        message = client.messages.create(**call_kwargs)
        latency_ms = (time.perf_counter() - start) * 1000
        text = "".join(
            block.text for block in message.content if getattr(block, "type", "") == "text"
        )
        parsed: Any = text
        if schema is not None:
            try:
                parsed = schema.model_validate(json.loads(strip_json_fences(text)))
            except (json.JSONDecodeError, ValueError):
                parsed = None
        usage = getattr(message, "usage", None)
        input_tokens = getattr(usage, "input_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "output_tokens", 0) if usage else 0
        cached_input = getattr(usage, "cache_read_input_tokens", 0) if usage else 0
        cost = (
            (input_tokens - cached_input) * self.pricing_per_million_tokens_in
            + output_tokens * self.pricing_per_million_tokens_out
        ) / 1_000_000
        _ = cache_key
        return GatewayResponse(
            vendor=self.vendor, model=self.model,
            output=parsed, raw_text=text,
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            cached_input_tokens=int(cached_input),
            cost_usd=float(cost), latency_ms=float(latency_ms),
            cache_hit=cached_input > 0,
            audit_id=f"audit:{message.id}" if hasattr(message, "id") else "audit:?",
            ttl_pinned=3600,
        )
