"""Planner: turn one research question into a validated :class:`ResearchPlan`.

The model output is treated as a *proposal*: ids are re-assigned (``Q1..Qn``),
the count is clipped to the depth profile, every sub-question is guaranteed
2-4 search queries, and priority ordering is enforced.  If the model fails to
return usable JSON the planner falls back to a deterministic decomposition so
the rest of the pipeline can still produce a report.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from ..errors import ConfigError
from ..models import Depth, ResearchPlan, SubQuestion
from . import prompts
from .caller import LlmCaller

__all__ = ["Planner"]

_MAX_QUERIES = 4
_MIN_QUERIES = 2

_FALLBACK_SUB_QUESTIONS = {
    "zh": [
        ("{question} 的现状与关键进展", "梳理时间线与标志性事件"),
        ("{question} 的核心数据与证据", "收集可验证的量化证据"),
        ("{question} 的挑战、风险与未来趋势", "评估不确定性与后续走向"),
    ],
    "en": [
        ("Current status and key developments of {question}", "Build a timeline of milestones"),
        ("Core data and evidence about {question}", "Collect verifiable quantitative evidence"),
        ("Challenges, risks and outlook of {question}", "Assess uncertainty and next steps"),
    ],
}

_QUERY_SUFFIXES = {
    "zh": ("", "最新进展", "核心数据", "权威报告"),
    "en": ("", "latest developments", "key data", "authoritative report"),
}

_SEARCH_STRATEGY = {
    "zh": "先检索权威媒体、学术论文与政府来源，再补充行业分析；关键数据交叉验证后再引用。",
    "en": "Start with authoritative media, academic papers and government sources, then add "
    "industry analysis; cross-check key numbers before citing them.",
}


def _language(value: str) -> str:
    return "en" if str(value or "zh").lower().startswith("en") else "zh"


def _as_text(value: Any, limit: int = 300) -> str:
    return " ".join(str(value or "").split())[:limit]


def _as_priority(value: Any) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return 1
    return max(1, number)


def fallback_queries(question: str, language: str = "zh") -> List[str]:
    """Deterministic query expansion used when the model gives too few queries."""
    lang = _language(language)
    question = _as_text(question, 220)
    suffixes = _QUERY_SUFFIXES[lang]
    return [f"{question} {suffix}".strip() for suffix in suffixes]


def _clean_queries(raw: Any) -> List[str]:
    queries: List[str] = []
    if isinstance(raw, (list, tuple, set)):
        for item in raw:
            text = _as_text(item, 220)
            if text and text.casefold() not in {q.casefold() for q in queries}:
                queries.append(text)
    elif isinstance(raw, str) and raw.strip():
        queries.append(_as_text(raw, 220))
    return queries


class Planner:
    """Builds a validated research plan from one ``TASK: plan`` LLM call."""

    def __init__(
        self,
        llm: Any,
        settings: Any,
        *,
        caller: Optional[LlmCaller] = None,
        language: Optional[str] = None,
    ) -> None:
        self.llm = llm
        self.settings = settings
        self.language = _language(language or settings.language)
        self.caller = caller if caller is not None else LlmCaller(llm, settings)
        self.profile = settings.profile()

    # ------------------------------------------------------------------ #
    def plan(self, question: str) -> ResearchPlan:
        """Return a normalised plan for ``question``; always has >= 1 sub-question."""
        question = " ".join(str(question or "").split())
        if not question:
            raise ConfigError("research question must not be empty")
        depth = Depth.parse(self.settings.depth)
        messages = prompts.plan_messages(
            question,
            language=self.language,
            depth=depth.value,
            max_sub_questions=self.profile.max_sub_questions,
            queries_per_question=self.profile.queries_per_question,
        )
        data = self.caller.complete_json(messages, label="plan")
        sub_questions = self._build_sub_questions(question, data)
        search_strategy = _as_text((data or {}).get("search_strategy"), 400)
        return ResearchPlan(
            question=question,
            language=self.language,
            depth=depth,
            sub_questions=sub_questions,
            search_strategy=search_strategy or _SEARCH_STRATEGY[self.language],
        )

    # ------------------------------------------------------------------ #
    def _build_sub_questions(
        self, question: str, data: Optional[Dict[str, Any]]
    ) -> List[SubQuestion]:
        raw_items: Sequence[Any] = []
        if isinstance(data, dict) and isinstance(data.get("sub_questions"), (list, tuple)):
            raw_items = list(data["sub_questions"])
        parsed: List[Dict[str, Any]] = []
        for index, item in enumerate(raw_items):
            if not isinstance(item, dict):
                continue
            text = _as_text(item.get("question"), 300)
            if not text:
                continue
            parsed.append(
                {
                    "question": text,
                    "rationale": _as_text(item.get("rationale"), 240),
                    "queries": _clean_queries(item.get("queries")),
                    "priority": _as_priority(item.get("priority", index + 1)),
                    "order": index,
                }
            )
        if not parsed:
            parsed = self._heuristic_items(question)

        # Stable sort: priority first, original order second (deterministic ids).
        parsed.sort(key=lambda entry: (entry["priority"], entry["order"]))
        parsed = parsed[: self.profile.max_sub_questions]
        target_queries = max(_MIN_QUERIES, min(self.profile.queries_per_question, _MAX_QUERIES))
        fallback = fallback_queries(question, self.language)
        sub_questions: List[SubQuestion] = []
        for index, entry in enumerate(parsed, 1):
            queries = list(entry["queries"])
            for candidate in fallback:
                if len(queries) >= target_queries:
                    break
                if candidate and candidate.casefold() not in {q.casefold() for q in queries}:
                    queries.append(candidate)
            # Last resort: the sub-question itself is always a valid query.
            while len(queries) < _MIN_QUERIES:
                if not queries:
                    candidate = entry["question"]
                else:
                    candidate = f"{entry['question']} {len(queries)}"
                queries.append(candidate)
            sub_questions.append(
                SubQuestion(
                    id=f"Q{index}",
                    question=entry["question"],
                    rationale=entry["rationale"],
                    queries=queries[:_MAX_QUERIES],
                    priority=entry["priority"],
                )
            )
        return sub_questions

    def _heuristic_items(self, question: str) -> List[Dict[str, Any]]:
        templates = _FALLBACK_SUB_QUESTIONS[self.language]
        items: List[Dict[str, Any]] = []
        for index, (template, rationale) in enumerate(templates):
            items.append(
                {
                    "question": template.format(question=question),
                    "rationale": rationale,
                    "queries": [],
                    "priority": index + 1,
                    "order": index,
                }
            )
        return items
