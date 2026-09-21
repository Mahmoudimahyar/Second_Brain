"""V1 model gateway (ADR-011). Vendor-portable LLMClient ABC + provider plugins.

Direct vendor SDK imports (`anthropic`, `openai`, `google.genai`) are banned
outside this package per dependency-rules.md / non-negotiable #9. The
`ruff flake8-tidy-imports` rule enforces this.
"""

from src.gateway.anthropic_adapter import AnthropicAdapter
from src.gateway.api import (
    GatewayResponse,
    LLMClient,
    MockProvider,
    ModelGateway,
    TaskID,
    default_gateway,
    strip_json_fences,
)
from src.gateway.gemini_adapter import GeminiAdapter
from src.gateway.openai_adapter import (
    OpenAIAdapter,
    nvidia_nim_adapter,
    together_adapter,
    xai_grok_adapter,
)

__all__ = [
    "AnthropicAdapter",
    "GatewayResponse",
    "GeminiAdapter",
    "LLMClient",
    "MockProvider",
    "ModelGateway",
    "OpenAIAdapter",
    "TaskID",
    "default_gateway",
    "nvidia_nim_adapter",
    "strip_json_fences",
    "together_adapter",
    "xai_grok_adapter",
]
