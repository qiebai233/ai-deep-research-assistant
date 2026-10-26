"""End-to-end tests for the agent pipeline (fully offline mock stack)."""

from __future__ import annotations

import json
import re
import unittest

from deepresearch.agent import Orchestrator
from deepresearch.errors import ConfigError
from deepresearch.fetch import MockFetcher
from deepresearch.llm import MockLLM
from deepresearch.models import Depth
from deepresearch.search import MockSearch
from tests.support import (
    BadJSONLLM,
    ExplodingSearch,
    RecordingLLM,
    collect_events,
    event_types,
    mock_settings,
)

QUESTION = "固态电池产业化进展如何？"
CITATION_RE = re.compile(r"\[(S\d+)\]")

REQUIRED_EVENTS = (
    "run_start",
    "plan_ready",
    "round_start",
    "search_done",
    "source_ready",
    "findings_ready",
    "outline_ready",
    "section_ready",
    "report_ready",
    "run_end",
)
TASK_NAMES = {"plan", "findings", "outline", "section", "meta"}


def run_pipeline(
    settings,
    *,
    llm=None,
    search=None,
    fetcher=None,
    question=QUESTION,
    **run_kwargs,
):
    """Run the orchestrator with the mock providers and return ``(result, sink)``."""
    sink = collect_events()
    orchestrator = Orchestrator(
        settings,
        llm=llm if llm is not None else MockLLM(),
        search=search if search is not None else MockSearch(settings),
        fetcher=fetcher if fetcher is not None else MockFetcher(settings),
        events=sink,
    )
    return orchestrator.run(question, **run_kwargs), sink


class EndToEndTests(unittest.TestCase):
    def test_standard_run_produces_cited_report(self) -> None:
        settings = mock_settings(depth="standard")
        result, sink = run_pipeline(settings)
        report = result.report
        state = result.state

        # --- plan ---
        self.assertEqual(state.plan.question, QUESTION)
        self.assertIsInstance(state.plan.depth, Depth)
        self.assertEqual(state.plan.depth, Depth.STANDARD)
        profile = settings.profile()
        self.assertGreaterEqual(len(state.plan.sub_questions), 1)
        self.assertLessEqual(len(state.plan.sub_questions), profile.max_sub_questions)
        for index, sub_question in enumerate(state.plan.sub_questions, 1):
            self.assertEqual(sub_question.id, f"Q{index}")
            self.assertTrue(sub_question.question)
            self.assertGreaterEqual(len(sub_question.queries), 2)
            self.assertLessEqual(len(sub_question.queries), 4)
        priorities = [sq.priority for sq in state.plan.sub_questions]
        self.assertEqual(priorities, sorted(priorities))

        # --- sources / findings ---
        self.assertGreater(len(state.sources), 0)
        self.assertLessEqual(len(state.sources), profile.max_sources)
        source_ids = set(state.sources)
        for source in state.sources.values():
            self.assertRegex(source.id, r"^S\d+$")
            self.assertEqual(source.status, "ok")
            self.assertTrue(source.url)
            self.assertTrue(source.domain)
            self.assertGreater(source.word_count, 0)
        self.assertGreater(len(state.findings), 0)
        self.assertLessEqual(len(state.findings), profile.max_findings)
        finding_ids = {finding.id for finding in state.findings}
        self.assertEqual(len(finding_ids), len(state.findings))
        for finding in state.findings:
            self.assertLessEqual(set(finding.source_ids), source_ids)
            self.assertGreaterEqual(finding.confidence, 0.0)
            self.assertLessEqual(finding.confidence, 1.0)

        # --- markdown structure & citations ---
        markdown = report.markdown
        for heading in (
            "## 摘要",
            "## 关键发现",
            "## 目录",
            "## 研究方法与局限",
            "## 参考文献",
        ):
            self.assertIn(heading, markdown)
        self.assertIn("> **研究问题**：", markdown)
        self.assertIn("生成时间", markdown)
        self.assertIn("---", markdown)
        self.assertIn("*由 DeepResearch v", markdown)
        self.assertTrue(report.title)
        self.assertTrue(report.summary)
        self.assertTrue(report.key_takeaways)
        self.assertTrue(report.limitations)
        self.assertTrue(report.sections)

        cited = set(CITATION_RE.findall(markdown))
        references = {source.id for source in report.references}
        self.assertTrue(cited)
        self.assertTrue(references)
        self.assertLessEqual(cited, references)
        self.assertLessEqual(references, source_ids)
        for section in report.sections:
            body_ids = list(dict.fromkeys(CITATION_RE.findall(section.body)))
            self.assertEqual(body_ids, section.source_ids)
            self.assertLessEqual(set(section.source_ids), source_ids)

        # --- usage ---
        usage = result.usage
        self.assertGreater(usage.llm_calls, 0)
        self.assertGreater(usage.search_calls, 0)
        self.assertGreater(usage.fetches, 0)
        self.assertGreater(usage.prompt_tokens + usage.completion_tokens, 0)
        self.assertGreaterEqual(usage.elapsed_seconds, 0.0)
        self.assertEqual(state.iteration, report.rounds)
        self.assertGreaterEqual(state.iteration, 1)

        # --- events ---
        types = event_types(sink)
        self.assertEqual(types[0], "run_start")
        self.assertEqual(types[-1], "run_end")
        for required in REQUIRED_EVENTS:
            self.assertIn(required, types)
        percentages = []
        for event in sink.history:
            self.assertIsNotNone(event.percent)
            self.assertGreaterEqual(event.percent, 0.0)
            self.assertLessEqual(event.percent, 100.0)
            percentages.append(event.percent)
            self.assertTrue(event.message)
            json.dumps(event.to_dict(), ensure_ascii=False)  # SSE/JSON-safe
        self.assertEqual(percentages, sorted(percentages))
        self.assertEqual(percentages[-1], 100.0)

    def test_depth_changes_budget(self) -> None:
        quick_result, quick_sink = run_pipeline(mock_settings(depth="quick"))
        std_result, std_sink = run_pipeline(mock_settings(depth="standard"))

        self.assertEqual(quick_result.state.plan.depth, Depth.QUICK)
        self.assertEqual(std_result.state.plan.depth, Depth.STANDARD)
        self.assertLessEqual(len(quick_result.state.plan.sub_questions), 3)
        self.assertLessEqual(len(quick_result.state.sources), 8)
        self.assertLessEqual(len(std_result.state.plan.sub_questions), 5)
        self.assertLessEqual(len(std_result.state.sources), 14)
        self.assertGreater(
            std_result.usage.llm_calls,
            quick_result.usage.llm_calls,
            "standard depth must spend more LLM calls than quick",
        )
        self.assertGreater(
            len(std_result.state.sources),
            len(quick_result.state.sources),
            "standard depth must gather more sources than quick",
        )
        self.assertIn("run_end", event_types(quick_sink))
        self.assertIn("run_end", event_types(std_sink))

    def test_depth_argument_overrides_settings(self) -> None:
        settings = mock_settings(depth="standard")
        result, _ = run_pipeline(settings, depth="quick")
        self.assertEqual(result.state.plan.depth, Depth.QUICK)
        self.assertLessEqual(len(result.state.plan.sub_questions), 3)

    def test_max_sources_setting_is_hard_cap(self) -> None:
        settings = mock_settings(depth="standard", max_sources=3)
        result, _ = run_pipeline(settings)
        self.assertLessEqual(len(result.state.sources), 3)

    def test_prompt_contract(self) -> None:
        recording = RecordingLLM(MockLLM())
        run_pipeline(mock_settings(depth="quick"), llm=recording)

        tasks = recording.tasks()
        self.assertEqual(tasks[0], "plan")
        self.assertEqual(tasks[-1], "meta")
        self.assertIn("outline", tasks)
        self.assertIn("section", tasks)
        self.assertIn("findings", tasks)
        self.assertEqual(set(tasks), TASK_NAMES)

        for call in recording.calls:
            user_messages = [message for message in call if message.role == "user"]
            self.assertTrue(user_messages)
            first_line = user_messages[-1].content.splitlines()[0]
            self.assertRegex(first_line, r"^TASK: (plan|findings|outline|section|meta)$")

        prompts = recording.prompts()
        by_task = {}
        for task, prompt in zip(tasks, prompts, strict=False):
            by_task.setdefault(task, []).append(prompt)
        self.assertIn("QUESTION:", by_task["plan"][0])
        self.assertIn("MAX_SUB_QUESTIONS:", by_task["plan"][0])
        findings_prompts = by_task["findings"]
        self.assertTrue(any("SUB_QUESTION: Q1" in prompt for prompt in findings_prompts))
        self.assertTrue(any(re.search(r"\[S\d+\]", prompt) for prompt in findings_prompts))
        self.assertIn("SECTION:", by_task["section"][0])
        self.assertIn("SECTIONS:", by_task["meta"][0])

    def test_bad_json_llm_falls_back_to_report(self) -> None:
        bad_llm = BadJSONLLM()
        result, sink = run_pipeline(mock_settings(depth="quick"), llm=bad_llm)

        self.assertGreater(bad_llm.calls, 0)
        self.assertTrue(result.report.markdown)
        self.assertIn("## 摘要", result.report.markdown)
        self.assertIn("## 参考文献", result.report.markdown)
        self.assertTrue(result.report.sections)
        self.assertIn("warning", event_types(sink))
        self.assertTrue(result.report.limitations)
        # Sources are still fetched even though the model never returns JSON.
        self.assertGreater(len(result.state.sources), 0)

    def test_exploding_search_does_not_crash(self) -> None:
        settings = mock_settings(depth="quick")
        result, sink = run_pipeline(settings, search=ExplodingSearch())

        self.assertTrue(result.report.markdown)
        self.assertIn("## 参考文献", result.report.markdown)
        self.assertEqual(len(result.state.sources), 0)
        self.assertEqual(result.report.references, [])
        self.assertEqual(result.usage.search_calls, 0)
        self.assertIn("warning", event_types(sink))
        self.assertTrue(result.report.limitations)

    def test_empty_question_raises_config_error(self) -> None:
        settings = mock_settings()
        for question in ("", "   ", "\n\t "):
            with self.assertRaises(ConfigError):
                run_pipeline(settings, question=question)

    def test_budget_soft_stop(self) -> None:
        settings = mock_settings(depth="quick", max_llm_calls=2)
        result, sink = run_pipeline(settings)

        self.assertLessEqual(result.usage.llm_calls, 2)
        self.assertTrue(result.report.markdown)
        self.assertTrue(result.report.limitations)
        self.assertTrue(
            any("上限" in item for item in result.report.limitations),
            result.report.limitations,
        )
        event_list = sink.history
        self.assertEqual(event_list[-1].type, "run_end")
        self.assertEqual(event_list[-1].percent, 100.0)

    def test_english_report(self) -> None:
        result, _ = run_pipeline(mock_settings(depth="quick"), language="en")

        self.assertEqual(result.report.language, "en")
        self.assertIn("## Summary", result.report.markdown)
        self.assertIn("## References", result.report.markdown)
        self.assertIn("Generated by DeepResearch v", result.report.markdown)
        self.assertNotIn("## 摘要", result.report.markdown)
        self.assertEqual(result.state.plan.language, "en")


if __name__ == "__main__":
    unittest.main()
