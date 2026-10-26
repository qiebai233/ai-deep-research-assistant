"""Orchestrator: the single public entry point of the agent pipeline.

Flow (matching ``CONTRACTS.md`` 2 and 6.1)::

    run_start -> plan_ready
      -> (round_start -> search_start/done -> source_ready* -> findings_ready
          -> gap_found*)*
      -> outline_ready -> section_ready* -> report_ready -> run_end

``percent`` is monotonically non-decreasing and always within ``0..100``.
Budgets are soft stops: the run still returns a report built from whatever was
gathered, and the reason is recorded in ``Report.limitations``.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from ..errors import ConfigError
from ..events import EventSink, EventType
from ..models import Depth, ResearchState, RunResult, UsageStats
from ..report.renderer import citation_order, disclaimer_for, render_markdown
from .caller import LlmCaller
from .planner import Planner
from .researcher import Researcher
from .writer import Writer

__all__ = ["Orchestrator"]

_MSG = {
    "zh": {
        "run_start": "开始深度调研：{question}",
        "plan_ready": "研究计划已生成：{count} 个子问题",
        "round_start": "开始第 {round}/{total} 轮调研",
        "outline_ready": "报告大纲已生成：{count} 个章节",
        "section_ready": "章节写作完成：{heading}",
        "report_ready": "报告已生成：{title}（{sources} 篇来源）",
        "run_end": "调研完成：{sources} 篇来源，用时 {elapsed:.2f}s",
        "empty_question": "研究问题不能为空",
        "bad_depth": "无效的深度参数：{depth}",
        "missing_evidence": "以下子问题未能获得可引用的直接证据：{ids}。",
        "no_sources": "本次运行未获取到可引用来源，报告主要基于模型已有知识。",
    },
    "en": {
        "run_start": "Research started: {question}",
        "plan_ready": "Research plan ready: {count} sub-questions",
        "round_start": "Research round {round}/{total}",
        "outline_ready": "Report outline ready: {count} sections",
        "section_ready": "Section written: {heading}",
        "report_ready": "Report ready: {title} ({sources} sources)",
        "run_end": "Research finished: {sources} sources in {elapsed:.2f}s",
        "empty_question": "research question must not be empty",
        "bad_depth": "invalid depth: {depth}",
        "missing_evidence": "These sub-questions lack citable evidence: {ids}.",
        "no_sources": "No citable sources were retrieved; the report relies on model "
        "knowledge only.",
    },
}


class Orchestrator:
    """Runs the full question -> report pipeline synchronously."""

    def __init__(
        self,
        settings: Any,
        *,
        llm: Any = None,
        search: Any = None,
        fetcher: Any = None,
        events: Optional[EventSink] = None,
    ) -> None:
        self.settings = settings
        self.events: EventSink = events if events is not None else EventSink()
        self._llm = llm
        self._search = search
        self._fetcher = fetcher
        self.usage = UsageStats()
        self._percent = 0.0
        self._language = "zh"
        self._budget_notes: List[str] = []
        self._started = time.monotonic()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def run(
        self,
        question: str,
        *,
        depth: Optional[str] = None,
        language: Optional[str] = None,
    ) -> RunResult:
        """Execute one research run and return its :class:`RunResult`."""
        question = " ".join(str(question or "").split())
        overrides: Dict[str, Any] = {}
        if depth is not None:
            try:
                overrides["depth"] = Depth.parse(depth).value
            except ValueError as exc:
                raise ConfigError(str(exc)) from exc
        if language is not None:
            overrides["language"] = language
        settings = self.settings.with_overrides(**overrides) if overrides else self.settings
        self._language = "en" if str(settings.language).lower().startswith("en") else "zh"
        if not question:
            raise ConfigError(self._msg("empty_question"))
        self.usage = UsageStats()
        self._percent = 0.0
        self._budget_notes = []
        self._started = time.monotonic()

        llm, search, fetcher = self._resolve_providers(settings)
        caller = LlmCaller(llm, settings, usage=self.usage, on_warning=self._warn)
        self._emit(
            EventType.RUN_START,
            self._msg("run_start").format(question=question),
            data={"question": question, "depth": settings.depth, "language": self._language},
            percent=0.0,
        )

        plan = Planner(llm, settings, caller=caller, language=self._language).plan(question)
        state = ResearchState(plan=plan)
        self._emit(
            EventType.PLAN_READY,
            self._msg("plan_ready").format(count=len(plan.sub_questions)),
            data={
                "depth": plan.depth.value,
                "sub_questions": [
                    {"id": sq.id, "question": sq.question, "priority": sq.priority}
                    for sq in plan.sub_questions
                ],
                "search_strategy": plan.search_strategy,
            },
            percent=8.0,
        )

        state.iteration = self._run_rounds(settings, caller, llm, search, fetcher, state)

        writer = Writer(llm, settings, caller=caller, language=self._language)
        outline = writer.build_outline(state)
        state.outline = outline
        self._emit(
            EventType.OUTLINE_READY,
            self._msg("outline_ready").format(count=len(outline)),
            data={"sections": [item.heading for item in outline]},
            percent=68.0,
        )

        sections = []
        total = max(1, len(outline))
        for index, item in enumerate(outline):
            section = writer.write_section(state, item, index=index, outline=outline)
            sections.append(section)
            self._emit(
                EventType.SECTION_READY,
                self._msg("section_ready").format(heading=section.heading),
                data={
                    "index": index + 1,
                    "heading": section.heading,
                    "source_ids": section.source_ids,
                },
                percent=72.0 + 18.0 * (index + 1) / total,
            )
        self._collect_budget(caller)

        meta = writer.build_meta(state, sections)
        limitations = list(meta.get("limitations") or [])
        limitations.extend(self._budget_notes)
        coverage = self._coverage_note(state)
        if coverage:
            limitations.append(coverage)
        report = writer.assemble(state, sections, meta, usage=self.usage, limitations=limitations)
        report.references = [
            state.sources[source_id]
            for source_id in citation_order(report)
            if source_id in state.sources and state.sources[source_id].status == "ok"
        ]
        report.disclaimer = disclaimer_for(self._language)
        # Optional metadata consumed by the renderer's one-line header.
        report.model = str(
            getattr(llm, "model", "") or getattr(llm, "name", "") or settings.llm_model
        )
        report.depth = plan.depth.value
        report.rounds = state.iteration
        report.usage = self.usage
        report.markdown = render_markdown(report)
        self.usage.elapsed_seconds = round(time.monotonic() - self._started, 4)

        source_count = len(state.ok_sources())
        self._emit(
            EventType.REPORT_READY,
            self._msg("report_ready").format(title=report.title, sources=source_count),
            data={
                "title": report.title,
                "sections": len(report.sections),
                "references": len(report.references),
                "sources": source_count,
            },
            percent=96.0,
        )
        self._emit(
            EventType.RUN_END,
            self._msg("run_end").format(sources=source_count, elapsed=self.usage.elapsed_seconds),
            data={
                "sources": source_count,
                "findings": len(state.findings),
                "rounds": state.iteration,
                "usage": self._usage_dict(),
            },
            percent=100.0,
        )
        return RunResult(report=report, state=state, usage=self.usage)

    # ------------------------------------------------------------------ #
    # Rounds
    # ------------------------------------------------------------------ #
    def _run_rounds(
        self,
        settings: Any,
        caller: LlmCaller,
        llm: Any,
        search: Any,
        fetcher: Any,
        state: ResearchState,
    ) -> int:
        profile = settings.profile()
        rounds = max(1, int(profile.max_rounds))
        span = 52.0 / rounds
        researcher = Researcher(
            llm,
            search,
            fetcher,
            settings,
            self.events,
            caller=caller,
            warn=self._warn,
            language=self._language,
        )
        round_index = 1
        executed = 0
        while round_index <= rounds:
            self._collect_budget(caller)
            if caller.exhausted():
                break
            base = 10.0 + (round_index - 1) * span
            self._emit(
                EventType.ROUND_START,
                self._msg("round_start").format(round=round_index, total=rounds),
                data={"round": round_index, "total_rounds": rounds},
                percent=base,
            )
            result = researcher.run_round(
                state,
                round_index=round_index,
                total_rounds=rounds,
                progress=self._emit,
                percent_base=base,
                percent_span=span,
            )
            executed = round_index
            state.iteration = round_index
            self._collect_budget(caller)
            if result.stop_reason:
                self._add_budget_note(result.stop_reason)
            if round_index >= rounds or not result.gaps:
                break
            round_index += 1
        return executed

    # ------------------------------------------------------------------ #
    # Providers / events / helpers
    # ------------------------------------------------------------------ #
    def _resolve_providers(self, settings: Any):
        llm = self._llm
        if llm is None:
            from ..llm import build_llm

            llm = build_llm(settings)
        search = self._search
        if search is None:
            from ..search import build_search

            search = build_search(settings)
        fetcher = self._fetcher
        if fetcher is None:
            from ..fetch import build_fetcher

            fetcher = build_fetcher(settings)
        return llm, search, fetcher

    def _emit(
        self,
        event_type: Any,
        message: str,
        *,
        data: Optional[Dict[str, Any]] = None,
        percent: Optional[float] = None,
    ) -> None:
        """Emit an event, keeping ``percent`` monotonic within ``0..100``."""
        if percent is not None:
            self._percent = max(self._percent, max(0.0, min(100.0, float(percent))))
        self.events.emit(event_type, message, data=data or {}, percent=self._percent)

    def _warn(self, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        self._emit(EventType.WARNING, message, data=data)

    def _collect_budget(self, caller: LlmCaller) -> None:
        if caller.stop_reason:
            self._add_budget_note(caller.stop_reason)

    def _add_budget_note(self, reason: str) -> None:
        if reason and reason not in self._budget_notes:
            self._budget_notes.append(reason)

    def _coverage_note(self, state: ResearchState) -> str:
        if not state.ok_sources():
            return self._msg("no_sources")
        covered = set(state.covered_sub_questions())
        missing = [sq.id for sq in state.plan.sub_questions if sq.id not in covered]
        if missing:
            return self._msg("missing_evidence").format(ids=", ".join(missing))
        return ""

    def _usage_dict(self) -> Dict[str, Any]:
        usage = self.usage
        return {
            "llm_calls": usage.llm_calls,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "search_calls": usage.search_calls,
            "fetches": usage.fetches,
            "fetch_failures": usage.fetch_failures,
            "elapsed_seconds": usage.elapsed_seconds,
            "est_cost_usd": usage.est_cost_usd,
        }

    def _msg(self, key: str) -> str:
        return _MSG[self._language][key]
