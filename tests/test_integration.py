"""End-to-end tests for the public API and artefact pipeline (fully offline)."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from deepresearch.api import run_research
from deepresearch.errors import ConfigError
from tests.support import collect_events, event_types, mock_settings, temp_dir

QUESTION = "固态电池 2025 年产业化进展如何？"


class RunResearchTests(unittest.TestCase):
    def test_full_mock_run_produces_cited_report(self) -> None:
        root = temp_dir()
        settings = mock_settings(root, depth="quick")
        sink = collect_events()

        result = run_research(QUESTION, settings=settings, events=sink)
        report = result.report

        # --- report shape ---
        self.assertTrue(report.title)
        self.assertIn("## 摘要", report.markdown)
        self.assertIn("## 关键发现", report.markdown)
        self.assertIn("## 参考文献", report.markdown)
        self.assertGreater(len(report.sections), 0)
        self.assertGreater(len(report.references), 0)

        # --- citations must resolve to real references ---
        cited = set(re.findall(r"\[(S\d+)\]", report.markdown))
        valid = {source.id for source in report.references}
        self.assertTrue(cited)
        self.assertLessEqual(cited, valid)

        # --- files ---
        self.assertIsNotNone(result.markdown_path)
        self.assertTrue(Path(result.markdown_path or "").is_file())
        self.assertTrue(Path(result.json_path or "").is_file())
        self.assertTrue(Path(result.trace_path or "").is_file())

        payload = json.loads(Path(result.json_path or "").read_text(encoding="utf-8"))
        self.assertEqual(payload["question"], QUESTION)
        self.assertEqual(payload["report"]["language"], "zh")
        trace_lines = Path(result.trace_path or "").read_text(encoding="utf-8").strip().splitlines()
        self.assertGreaterEqual(len(trace_lines), 5)
        self.assertEqual(json.loads(trace_lines[0])["type"], "run_start")

        # --- events ---
        types = event_types(sink)
        self.assertEqual(types[0], "run_start")
        self.assertEqual(types[-1], "run_end")
        for required in ("plan_ready", "outline_ready", "report_ready", "section_ready"):
            self.assertIn(required, types)
        self.assertTrue(any(t.startswith("search") or t == "findings_ready" for t in types))

        # --- usage ---
        self.assertGreater(result.usage.llm_calls, 0)
        self.assertGreater(result.usage.prompt_tokens + result.usage.completion_tokens, 0)
        self.assertGreater(result.usage.elapsed_seconds, 0)

        # --- state ---
        self.assertEqual(result.state.plan.question, QUESTION)
        self.assertGreaterEqual(len(result.state.plan.sub_questions), 2)
        self.assertTrue(result.state.sources)

    def test_save_false_writes_nothing(self) -> None:
        root = temp_dir()
        settings = mock_settings(root)
        result = run_research("无保存测试", settings=settings, save=False)
        self.assertIsNone(result.markdown_path)
        self.assertFalse((Path(root) / "reports").exists())
        self.assertTrue(result.report.markdown)

    def test_depth_limits_are_enforced(self) -> None:
        quick = run_research(
            "深度预算测试", settings=mock_settings(temp_dir(), depth="quick"), save=False
        )
        standard = run_research(
            "深度预算测试", settings=mock_settings(temp_dir(), depth="standard"), save=False
        )
        self.assertLessEqual(len(quick.state.plan.sub_questions), 3)
        self.assertLessEqual(len(quick.state.sources), 8)
        self.assertLessEqual(len(standard.state.plan.sub_questions), 5)
        self.assertLessEqual(len(standard.state.sources), 14)
        self.assertLessEqual(quick.usage.llm_calls, standard.usage.llm_calls)

    def test_blank_question_rejected(self) -> None:
        with self.assertRaises(ConfigError):
            run_research("   ", settings=mock_settings())
        with self.assertRaises(ConfigError):
            run_research("", settings=mock_settings())

    def test_english_report(self) -> None:
        result = run_research(
            "What is the state of solid-state batteries?",
            settings=mock_settings(temp_dir(), language="en"),
            language="en",
            save=False,
        )
        self.assertEqual(result.report.language, "en")
        self.assertTrue(result.report.markdown)


if __name__ == "__main__":
    unittest.main()
