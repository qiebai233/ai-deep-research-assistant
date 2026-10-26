"""Language-model provider interface.

A provider is anything with a ``name`` and a synchronous ``complete`` method.
Two implementations ship with DeepResearch:

* :class:`~deepresearch.llm.openai_compat.OpenAICompatLLM` — any
  OpenAI-compatible ``/chat/completions`` endpoint (OpenAI, DeepSeek, Moonshot,
  Qwen/DashScope compatible mode, OpenRouter, vLLM, Ollama, LM Studio, ...).
* :class:`~deepresearch.llm.mock.MockLLM` — a deterministic, network-free model
  used by the offline demo, the test-suite and CI.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence, runtime_checkable

from ..errors import LLMError

__all__ = [
    "LLMClient",
    "LLMResponse",
    "Message",
    "extract_json",
    "json_or_raise",
]


@dataclass
class Message:
    role: str  # system | user | assistant
    content: str

    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class LLMResponse:
    text: str
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    finish_reason: str = ""
    raw: Optional[Dict[str, Any]] = field(default=None, repr=False)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@runtime_checkable
class LLMClient(Protocol):
    """Protocol implemented by every LLM provider."""

    name: str

    def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> LLMResponse: ...


_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    """Best-effort extraction of a JSON value from an LLM answer.

    Handles bare JSON, fenced code blocks (```json ... ```), and prose wrapped
    around a single object/array.  Raises :class:`LLMError` when nothing parses.
    """
    if text is None:
        raise LLMError("empty LLM response")
    candidates: List[str] = [text.strip()]
    candidates.extend(match.group(1).strip() for match in _FENCE_RE.finditer(text))
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            candidates.append(text[start : end + 1])

    for candidate in candidates:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise LLMError(f"could not parse JSON from model output: {text[:400]!r}")


def json_or_raise(text: str, *, expect: str = "object") -> Dict[str, Any]:
    """Parse JSON and assert the top-level shape, with a helpful error message."""
    value = extract_json(text)
    if expect == "object" and not isinstance(value, dict):
        raise LLMError(f"expected a JSON object, got {type(value).__name__}")
    if expect == "array" and not isinstance(value, list):
        raise LLMError(f"expected a JSON array, got {type(value).__name__}")
    return value
