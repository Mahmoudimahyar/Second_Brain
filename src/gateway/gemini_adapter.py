"""Gemini (google.genai) provider for `LLMClient`. Confined to `src/gateway/`."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from src.gateway.api import GatewayResponse, strip_json_fences


@dataclass
class GeminiAdapter:
    """Gemini provider. Default model = Gemini 2.5 Flash-Lite (cheapest tier;
    used for Pass 3 cluster summaries + Pass 4 broad sentiment per ADR-011).
    """

    vendor: str = "gemini"
    model: str = "gemini-2.5-flash-lite"
    api_key_env: str = "GEMINI_API_KEY"
    pricing_per_million_tokens_in: float = 0.075
    pricing_per_million_tokens_out: float = 0.30
    _client: Any | None = field(default=None, init=False, repr=False)

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google import genai  # noqa: PLC0415 — optional SDK, lazy import by design
        except ImportError as e:  # pragma: no cover
            raise ImportError(
                "GeminiAdapter requires the `google-genai` SDK. "
                "Install with `pip install google-genai`.",
            ) from e
        self._client = genai.Client()
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
        response = client.models.generate_content(  # pragma: no cover
            model=self.model, contents=prompt,
        )
        latency_ms = (time.perf_counter() - start) * 1000
        text = response.text if hasattr(response, "text") else ""
        parsed: Any = text
        if schema is not None:
            try:
                parsed = schema.model_validate(json.loads(strip_json_fences(text)))
            except (json.JSONDecodeError, ValueError):
                parsed = None
        usage = getattr(response, "usage_metadata", None)
        input_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
        output_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0
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
            cache_hit=False, audit_id="audit:gemini",
            ttl_pinned=3600,
        )
