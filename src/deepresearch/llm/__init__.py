"""LLM provider factory.

``build_llm`` maps ``Settings.llm_provider`` to a concrete synchronous client:

* ``mock`` — :class:`~deepresearch.llm.mock.MockLLM`, fully offline.
* ``deepseek`` / ``openai`` / ``openrouter`` / ``ollama`` / ``custom`` — any
  OpenAI-compatible ``/chat/completions`` endpoint via
  :class:`~deepresearch.llm.openai_compat.OpenAICompatLLM`.

Unknown providers raise :class:`~deepresearch.errors.ConfigError` so the CLI can
show an actionable message instead of failing later mid-run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ..config import PRESETS, Settings
from ..errors import ConfigError
from .base import LLMClient, LLMResponse, Message, extract_json, json_or_raise
from .mock import MockLLM
from .openai_compat import OpenAICompatLLM

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..http import HttpClient

__all__ = [
    "LLMClient",
    "LLMResponse",
    "Message",
    "MockLLM",
    "OpenAICompatLLM",
    "build_llm",
    "extract_json",
    "json_or_raise",
]

#: Providers that speak the OpenAI chat-completion protocol.
OPENAI_COMPAT_PROVIDERS = frozenset({"deepseek", "openai", "openrouter", "ollama", "custom"})


def build_llm(settings: Settings, *, http: Optional["HttpClient"] = None) -> LLMClient:
    """Create the LLM client described by ``settings``.

    Raises :class:`ConfigError` when the provider is unknown, the endpoint is
    missing, or a required API key was not configured.  ``http`` is injectable
    for tests and never hits the network on its own.
    """
    provider = str(getattr(settings, "llm_provider", "") or "mock").strip().lower()
    if provider == "mock":
        return MockLLM()
    if provider in OPENAI_COMPAT_PROVIDERS:
        if not str(getattr(settings, "llm_base_url", "") or "").strip():
            raise ConfigError(
                f"LLM provider {provider!r} needs a base URL; "
                "set DEEPRESEARCH_LLM_BASE_URL or choose a built-in preset."
            )
        if provider != "ollama" and not str(getattr(settings, "llm_api_key", "") or "").strip():
            key_env = PRESETS.get(provider, {}).get("key_env") or "DEEPRESEARCH_LLM_API_KEY"
            raise ConfigError(
                f"LLM provider {provider!r} needs an API key. Set {key_env} "
                "in your environment or .env file (see .env.example)."
            )
        return OpenAICompatLLM(settings, http=http)
    allowed = ", ".join(["mock", *sorted(OPENAI_COMPAT_PROVIDERS)])
    raise ConfigError(f"unknown llm provider {provider!r}; choose from: {allowed}")
