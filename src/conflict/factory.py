"""Builders for the conflict resolver's collaborators (ADR-024 judge, ADR-016
web-verifier), constructed from env-configured providers.

GAP-052: the resolver was historically built bare (`ConflictResolver()`), so
same-tier ties went straight to HITL and web-verify never fired. These builders
let the real entrypoints construct it WITH a judge + web-verifier. They return
``None`` when prerequisites (vendor keys / `TAVILY_API_KEY`) are absent, so the
resolver degrades to HITL rather than crashing — the wiring is real; the
collaborators are best-effort on key availability.
"""

from __future__ import annotations

import os

from src.conflict.judge import ThreeVendorJudge, _family_of
from src.conflict.web_verify import WebVerificationAgent
from src.gateway.api import LLMClient


def build_three_vendor_judge(*, minimum_agreement: int = 2) -> ThreeVendorJudge | None:
    """3-vendor LLM-as-judge panel (Sonnet 4.6 + Gemini 2.5 Flash + GPT-4.1-mini,
    ADR-024/006) from whichever vendor keys are present. ``None`` if fewer than
    3 distinct vendor families are available.
    """

    from src.gateway.anthropic_adapter import AnthropicAdapter  # noqa: PLC0415
    from src.gateway.gemini_adapter import GeminiAdapter  # noqa: PLC0415
    from src.gateway.openai_adapter import OpenAIAdapter  # noqa: PLC0415

    clients: list[LLMClient] = []
    if os.environ.get("ANTHROPIC_API_KEY"):
        clients.append(AnthropicAdapter(model="claude-sonnet-4-6"))
    if os.environ.get("OPENAI_API_KEY"):
        clients.append(OpenAIAdapter(model="gpt-4.1-mini"))
    if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        clients.append(GeminiAdapter(model="gemini-2.5-flash"))

    families = {_family_of(c.vendor) for c in clients}
    if len(clients) < 3 or len(families) < 3:
        return None
    return ThreeVendorJudge(clients=clients, minimum_agreement=minimum_agreement)


def build_web_verifier() -> WebVerificationAgent | None:
    """Tavily-backed 3-signal web-verifier (ADR-016 v2). ``None`` when
    ``TAVILY_API_KEY`` is absent."""

    if not os.environ.get("TAVILY_API_KEY"):
        return None
    from src.conflict.providers.tavily import TavilyProvider  # noqa: PLC0415

    return WebVerificationAgent(provider=TavilyProvider())
