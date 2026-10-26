"""Shared LLM invocation helper: budgets, usage accounting and JSON handling.

Every agent stage calls the model through one :class:`LlmCaller`, so that:

* ``UsageStats`` is updated in exactly one place (tokens, calls, estimated cost);
* ``max_llm_calls`` / ``max_cost_usd`` / ``max_seconds`` are enforced with a
  *soft* stop (the pipeline keeps running on deterministic heuristics);
* invalid JSON is retried once with an explicit ``Return valid JSON only`` hint
  and then silently degrades to the caller's heuristic fallback.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Sequence

from ..errors import LLMError
from ..llm.base import LLMResponse, Message, json_or_raise
from ..models import UsageStats

__all__ = ["JSON_RETRY_HINT", "LlmCaller"]

JSON_RETRY_HINT = "Return valid JSON only."

_SOFT_STOP = {
    "zh": {
        "llm_calls": "LLM 调用次数达到上限（max_llm_calls={value}），后续内容使用启发式兜底。",
        "cost": "预估成本达到上限（max_cost_usd=${value}），后续内容使用启发式兜底。",
        "seconds": "运行时长达到上限（max_seconds={value}s），后续内容使用启发式兜底。",
        "failed": "LLM 调用失败（{label}）：{error}；已使用启发式兜底继续。",
        "bad_json": "LLM 返回内容无法解析为 JSON（{label}）；已重试一次并使用启发式兜底。",
    },
    "en": {
        "llm_calls": "LLM call budget exhausted (max_llm_calls={value}); "
        "remaining content uses heuristic fallbacks.",
        "cost": "Cost budget exhausted (max_cost_usd=${value}); "
        "remaining content uses heuristic fallbacks.",
        "seconds": "Time budget exhausted (max_seconds={value}s); "
        "remaining content uses heuristic fallbacks.",
        "failed": "LLM call failed ({label}): {error}; continuing with a heuristic fallback.",
        "bad_json": "LLM output was not valid JSON ({label}); retried once and fell back "
        "to heuristics.",
    },
}


def _lang(settings: Any) -> str:
    return "en" if str(getattr(settings, "language", "zh")).lower().startswith("en") else "zh"


class LlmCaller:
    """Budget-aware wrapper around an :class:`~deepresearch.llm.base.LLMClient`."""

    def __init__(
        self,
        llm: Any,
        settings: Any,
        *,
        usage: Optional[UsageStats] = None,
        on_warning: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.llm = llm
        self.settings = settings
        self.usage = usage if usage is not None else UsageStats()
        self.on_warning = on_warning
        self.started = time.monotonic()
        self.stop_reason: Optional[str] = None
        self.warnings: List[str] = []
        self._lang = _lang(settings)

    # ------------------------------------------------------------------ #
    # Budget
    # ------------------------------------------------------------------ #
    def _text(self, key: str, **kwargs: Any) -> str:
        template = _SOFT_STOP[self._lang][key]
        return template.format(**kwargs)

    def elapsed(self) -> float:
        """Seconds elapsed since this caller was created."""
        return time.monotonic() - self.started

    def budget_reason(self) -> Optional[str]:
        """Return (and remember) the first exhausted budget, or ``None``."""
        if self.stop_reason:
            return self.stop_reason
        settings, usage = self.settings, self.usage
        max_calls = int(getattr(settings, "max_llm_calls", 0) or 0)
        max_cost = float(getattr(settings, "max_cost_usd", 0.0) or 0.0)
        max_seconds = float(getattr(settings, "max_seconds", 0.0) or 0.0)
        reason: Optional[str] = None
        if max_calls and usage.llm_calls >= max_calls:
            reason = self._text("llm_calls", value=max_calls)
        elif max_cost and usage.est_cost_usd >= max_cost:
            reason = self._text("cost", value=max_cost)
        elif max_seconds and self.elapsed() >= max_seconds:
            reason = self._text("seconds", value=max_seconds)
        if reason:
            self.stop_reason = reason
            self.warn(reason)
        return reason

    def exhausted(self) -> bool:
        """True once any budget is exhausted (a soft stop, never an exception)."""
        return self.budget_reason() is not None

    # ------------------------------------------------------------------ #
    # Warnings
    # ------------------------------------------------------------------ #
    def warn(self, message: str) -> None:
        """Record a warning and forward it to the event sink (once per message)."""
        if not message or message in self.warnings:
            return
        self.warnings.append(message)
        if self.on_warning is not None:
            try:
                self.on_warning(message)
            except Exception:  # pragma: no cover - observers must never break a run
                pass

    # ------------------------------------------------------------------ #
    # Calls
    # ------------------------------------------------------------------ #
    def complete(
        self,
        messages: Sequence[Message],
        *,
        json_mode: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        label: str = "",
    ) -> Optional[LLMResponse]:
        """Call the model once, accounting for tokens/cost; ``None`` when skipped."""
        if self.exhausted():
            return None
        kwargs: Dict[str, Any] = {
            "json_mode": json_mode,
            "temperature": (
                float(getattr(self.settings, "llm_temperature", 0.3))
                if temperature is None
                else temperature
            ),
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        try:
            response = self.llm.complete(messages, **kwargs)
        except LLMError as exc:
            self.warn(self._text("failed", label=label or "unknown", error=str(exc)[:200]))
            return None
        self._record(response)
        return response

    def _record(self, response: LLMResponse) -> None:
        self.usage.llm_calls += 1
        prompt_tokens = int(getattr(response, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(response, "completion_tokens", 0) or 0)
        self.usage.prompt_tokens += max(0, prompt_tokens)
        self.usage.completion_tokens += max(0, completion_tokens)
        self.usage.est_cost_usd += float(
            self.settings.estimate_cost(prompt_tokens, completion_tokens)
        )

    def complete_json(
        self,
        messages: Sequence[Message],
        *,
        label: str = "",
        expect: str = "object",
    ) -> Optional[Dict[str, Any]]:
        """Call the model in JSON mode, parse it, retry once, then give up.

        A ``None`` result is expected and handled by every stage with a
        deterministic heuristic fallback.
        """
        response = self.complete(messages, json_mode=True, label=label)
        if response is None:
            return None
        try:
            return json_or_raise(response.text, expect=expect)
        except LLMError:
            pass

        retry_messages = [Message(role=m.role, content=m.content) for m in messages]
        if retry_messages and retry_messages[-1].role == "user":
            retry_messages[-1] = Message(
                role="user", content=retry_messages[-1].content + "\n\n" + JSON_RETRY_HINT
            )
        else:
            retry_messages.append(Message(role="user", content=JSON_RETRY_HINT))
        retry = self.complete(retry_messages, json_mode=True, label=f"{label}:retry")
        if retry is not None:
            try:
                return json_or_raise(retry.text, expect=expect)
            except LLMError:
                pass
        self.warn(self._text("bad_json", label=label or "unknown"))
        return None
