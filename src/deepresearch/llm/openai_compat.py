"""Client for any OpenAI-compatible ``/chat/completions`` endpoint.

One implementation covers every hosted or self-hosted provider that speaks the
OpenAI chat protocol: OpenAI, DeepSeek, OpenRouter, Ollama (``/v1``), vLLM,
LM Studio, DashScope compatible mode, ...  The only transport used is
:class:`deepresearch.http.HttpClient`, so retries, timeouts and byte caps behave
exactly like the rest of DeepResearch.

Security note: the API key is sent in the ``Authorization`` header only and is
redacted from every error message returned to callers or written to logs.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional, Sequence

from ..config import Settings
from ..errors import ConfigError, LLMError
from ..http import DEFAULT_USER_AGENT, HttpClient, HttpError
from .base import LLMResponse, Message

__all__ = ["OpenAICompatLLM"]

#: Providers that legitimately run without an API key (local daemons).
_KEYLESS_PROVIDERS = {"ollama"}

_MAX_ERROR_CHARS = 300


class OpenAICompatLLM:
    """Synchronous LLM client for OpenAI-compatible chat-completion APIs."""

    def __init__(self, settings: Settings, http: Optional[HttpClient] = None) -> None:
        self.settings = settings
        provider = (settings.llm_provider or "custom").strip().lower()
        self._api_key = (settings.llm_api_key or "").strip()
        self._base_url = (settings.llm_base_url or "").strip().rstrip("/")
        if not self._base_url:
            raise ConfigError(
                f"LLM provider {provider!r} needs a base URL "
                "(set DEEPRESEARCH_LLM_BASE_URL or use a built-in preset)"
            )
        if provider not in _KEYLESS_PROVIDERS and not self._api_key:
            raise ConfigError(
                f"LLM provider {provider!r} needs an API key "
                "(set DEEPRESEARCH_LLM_API_KEY or the provider-specific variable)"
            )
        self.name = f"openai-compat/{settings.llm_model}"
        self.model = settings.llm_model
        self.timeout = float(settings.llm_timeout or 60.0)
        self.http = http or HttpClient(
            user_agent=settings.user_agent or DEFAULT_USER_AGENT,
            timeout=self.timeout,
            max_retries=max(0, int(settings.llm_max_retries or 0)),
        )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    @property
    def endpoint(self) -> str:
        """Absolute URL of the chat-completions endpoint."""
        return f"{self._base_url}/chat/completions"

    def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Call the endpoint once and return the decoded completion."""
        if not messages:
            raise LLMError("no messages supplied to the LLM")
        payload = self._payload(messages, temperature, max_tokens, json_mode)
        started = time.perf_counter()
        try:
            response = self.http.post_json(
                self.endpoint,
                payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except HttpError as exc:
            raise self._to_llm_error(exc) from exc
        latency_s = time.perf_counter() - started
        try:
            data = response.json()
        except HttpError as exc:  # invalid JSON body
            detail = self._redact(_body_summary(response.text))
            raise LLMError(
                f"LLM endpoint returned invalid JSON (HTTP {response.status})"
                + (f": {detail}" if detail else "")
            ) from exc
        return self._parse(data, latency_s)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"OpenAICompatLLM(name={self.name!r}, endpoint={self.endpoint!r})"

    # ------------------------------------------------------------------ #
    # Request helpers
    # ------------------------------------------------------------------ #
    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _payload(
        self,
        messages: Sequence[Message],
        temperature: float,
        max_tokens: Optional[int],
        json_mode: bool,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": [message.to_dict() for message in messages],
            "temperature": float(temperature),
            "stream": False,
        }
        limit = self.settings.llm_max_tokens or 0
        if max_tokens is not None and int(max_tokens) > 0:
            limit = int(max_tokens)
        if limit > 0:
            payload["max_tokens"] = limit
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    # ------------------------------------------------------------------ #
    # Response / error parsing
    # ------------------------------------------------------------------ #
    def _parse(self, data: Any, latency_s: float) -> LLMResponse:
        if not isinstance(data, dict):
            raise LLMError(f"unexpected LLM response type: {type(data).__name__}")
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            detail = self._redact(_json_summary(data))
            raise LLMError("LLM response has no choices" + (f": {detail}" if detail else ""))
        choice = choices[0] if isinstance(choices[0], dict) else {}
        message = choice.get("message")
        content = ""
        if isinstance(message, dict):
            content = _content_to_text(message.get("content"))
        if not content.strip():
            raise LLMError("LLM response contained empty completion content")
        usage = data.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        return LLMResponse(
            text=content,
            model=str(data.get("model") or self.settings.llm_model),
            prompt_tokens=_as_int(usage.get("prompt_tokens")),
            completion_tokens=_as_int(usage.get("completion_tokens")),
            latency_s=round(latency_s, 4),
            finish_reason=str(choice.get("finish_reason") or ""),
            raw=data,
        )

    def _to_llm_error(self, exc: HttpError) -> LLMError:
        """Map an :class:`HttpError` to a key-free :class:`LLMError`."""
        detail = _body_summary(exc.body) or str(exc)
        detail = self._redact(detail)
        prefix = "LLM request failed"
        if exc.status is not None:
            prefix = f"LLM request failed (HTTP {exc.status})"
        message = f"{prefix}: {detail}" if detail else prefix
        return LLMError(message)

    def _redact(self, text: str) -> str:
        """Collapse whitespace, truncate and remove the API key from ``text``."""
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        if self._api_key:
            text = text.replace(self._api_key, "***")
        if len(text) > _MAX_ERROR_CHARS:
            text = text[: _MAX_ERROR_CHARS - 1].rstrip() + "…"
        return text


# --------------------------------------------------------------------------- #
# Small parsing helpers
# --------------------------------------------------------------------------- #
def _content_to_text(content: Any) -> str:
    """Normalise a ``message.content`` value (string or multimodal parts)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
            elif isinstance(part, str):
                parts.append(part)
        return "".join(parts)
    return ""


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _body_summary(body: str) -> str:
    return re.sub(r"\s+", " ", str(body or "")).strip()[:_MAX_ERROR_CHARS]


def _json_summary(data: Any) -> str:
    try:
        return _body_summary(json.dumps(data, ensure_ascii=False))
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return _body_summary(repr(data))
