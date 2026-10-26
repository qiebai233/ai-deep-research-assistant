"""Tests for artefact persistence."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from deepresearch.events import ProgressEvent
from deepresearch.models import (
    Depth,
    Report,
    ReportSection,
    ResearchPlan,
    ResearchState,
    RunResult,
    SubQuestion,
    UsageStats,
)
from deepresearch.storage import run_directory, save_run, slugify
from tests.support import temp_workspace


def make_result(question: str = "固态电池产业化进展如何？") -> RunResult:
    plan = ResearchPlan(
        question=question,
        depth=Depth.QUICK,
        sub_questions=[SubQuestion(id="Q1", question="技术路线", queries=["固态电池 技术路线"])],
    )
    state = ResearchState(plan=plan, iteration=1)
    report = Report(
        question=question,
        title="固态电池产业化进展",
        language="zh",
        summary="摘要内容。",
        key_takeaways=["要点一", "要点二"],
        sections=[ReportSection(heading="技术路线", body="正文 [S1]。", source_ids=["S1"])],
        markdown="# 固态电池产业化进展\n\n> 元信息\n\n## 摘要\n\n摘要内容。\n",
        usage=UsageStats(llm_calls=3),
    )
    return RunResult(report=report, state=state, usage=UsageStats(llm_calls=3))


class SlugTests(unittest.TestCase):
    def test_keeps_cjk_and_shortens(self) -> None:
        self.assertEqual(slugify("固态电池 产业化进展"), "固态电池-产业化进展")
        self.assertEqual(slugify("a/b\\c: d"), "a-b-c-d")
        self.assertEqual(slugify(""), "research")
        self.assertLessEqual(len(slugify("长" * 300)), 40)

    def test_run_directory_is_unique(self) -> None:
        with temp_workspace() as tmp:
            first = run_directory(tmp, "same question")
            second = run_directory(tmp, "same question")
            self.assertNotEqual(first, second)
            self.assertTrue(first.is_dir() and second.is_dir())
            self.assertTrue(first.name.endswith("same-question"))


class SaveRunTests(unittest.TestCase):
    def test_writes_all_artefacts(self) -> None:
        with temp_workspace() as tmp:
            result = make_result()
            events = [
                ProgressEvent("run_start", "开始"),
                ProgressEvent("report_ready", "完成", percent=100.0),
            ]
            saved = save_run(result, tmp, trace_events=events)
            directory = Path(saved.out_dir or "")

            self.assertTrue(directory.is_dir())
            self.assertEqual(
                Path(saved.markdown_path or "").read_text(encoding="utf-8"), result.report.markdown
            )
            payload = json.loads(Path(saved.json_path or "").read_text(encoding="utf-8"))
            self.assertEqual(payload["question"], result.report.question)
            self.assertEqual(payload["report"]["title"], "固态电池产业化进展")
            self.assertEqual(payload["state"]["plan"]["depth"], "quick")
            self.assertEqual(payload["schema_version"], 1)

            trace_lines = (
                Path(saved.trace_path or "").read_text(encoding="utf-8").strip().splitlines()
            )
            self.assertEqual(len(trace_lines), 2)
            self.assertEqual(json.loads(trace_lines[0])["type"], "run_start")
            self.assertEqual(json.loads(trace_lines[1])["percent"], 100.0)

    def test_optional_artefacts_can_be_disabled(self) -> None:
        with temp_workspace() as tmp:
            result = save_run(make_result(), tmp, want_json=False, want_trace=False)
            directory = Path(result.out_dir or "")
            self.assertIsNone(result.json_path)
            self.assertIsNone(result.trace_path)
            self.assertEqual(sorted(p.name for p in directory.iterdir()), ["report.md"])

    def test_missing_markdown_is_rendered(self) -> None:
        with temp_workspace() as tmp:
            result = make_result()
            result.report.markdown = ""
            saved = save_run(result, tmp)
            self.assertTrue(saved.report.markdown)
            self.assertIn("## 摘要", saved.report.markdown)

    def test_settings_metadata_written_when_given(self) -> None:
        from tests.support import mock_settings

        with temp_workspace() as tmp:
            saved = save_run(make_result(), tmp, settings=mock_settings(tmp))
            payload = json.loads(Path(saved.json_path or "").read_text(encoding="utf-8"))
            self.assertEqual(payload["settings"]["llm_provider"], "mock")


if __name__ == "__main__":
    unittest.main()
