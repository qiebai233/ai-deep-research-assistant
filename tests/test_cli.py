"""CLI tests: these exercise the real command line, the mock stack and exit codes."""

from __future__ import annotations

import unittest
from pathlib import Path

from tests.support import run_cli, temp_dir

MOCK_ENV = {
    "DEEPRESEARCH_LLM_PROVIDER": "mock",
    "DEEPRESEARCH_SEARCH_PROVIDER": "mock",
    "DEEPRESEARCH_LLM_MODEL": "mock-researcher",
}
SECRET_VARS = (
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "LLM_API_KEY",
    "DEEPRESEARCH_LLM_API_KEY",
    "TAVILY_API_KEY",
)


class VersionAndProvidersTests(unittest.TestCase):
    def test_version(self) -> None:
        result = run_cli(["version"])
        self.assertEqual(result.exit_code, 0, result.stderr)
        self.assertIn("deepresearch 0.1.0", result.stdout)
        self.assertIn("Python", result.stdout)
        self.assertIn("无（仅标准库）", result.stdout)

    def test_providers_lists_presets(self) -> None:
        result = run_cli(["providers"], env=MOCK_ENV, clear_env=SECRET_VARS)
        self.assertEqual(result.exit_code, 0, result.stderr)
        for expected in ("deepseek", "openai", "ollama", "tavily", "searxng", "mock"):
            self.assertIn(expected, result.stdout)

    def test_no_command_prints_help(self) -> None:
        result = run_cli([])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("run", result.stdout)
        self.assertIn("serve", result.stdout)


class InitTests(unittest.TestCase):
    def test_init_creates_env_template(self) -> None:
        target = Path(temp_dir()) / ".env"
        result = run_cli(["init", "--output", str(target)])
        self.assertEqual(result.exit_code, 0, result.stderr)
        self.assertTrue(target.exists())
        content = target.read_text(encoding="utf-8")
        self.assertIn("DEEPRESEARCH_LLM_PROVIDER", content)
        self.assertIn("TAVILY_API_KEY", content)
        self.assertIn("DEEPRESEARCH_LLM_API_KEY", content)

    def test_init_refuses_to_overwrite_without_force(self) -> None:
        target = Path(temp_dir()) / ".env"
        target.write_text("KEEP=1\n", encoding="utf-8")
        result = run_cli(["init", "--output", str(target)])
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(target.read_text(encoding="utf-8"), "KEEP=1\n")

        forced = run_cli(["init", "--output", str(target), "--force"])
        self.assertEqual(forced.exit_code, 0, forced.stderr)
        self.assertIn("DEEPRESEARCH_LLM_PROVIDER", target.read_text(encoding="utf-8"))


class RunCommandTests(unittest.TestCase):
    def test_offline_demo_writes_report(self) -> None:
        out_dir = Path(temp_dir()) / "reports"
        result = run_cli(
            ["run", "--demo", "--out", str(out_dir), "--quiet", "固态电池产业化进展如何？"],
            env=MOCK_ENV,
            clear_env=SECRET_VARS,
        )
        self.assertEqual(result.exit_code, 0, result.stderr)
        self.assertIn("报告：", result.stdout)
        reports = list(out_dir.glob("*/report.md"))
        self.assertEqual(len(reports), 1)
        markdown = reports[0].read_text(encoding="utf-8")
        self.assertIn("## 参考文献", markdown)
        self.assertIn("## 摘要", markdown)

    def test_stdout_mode_emits_markdown_only(self) -> None:
        result = run_cli(
            ["run", "--demo", "--stdout", "--no-save", "量子计算最新进展"],
            env=MOCK_ENV,
            clear_env=SECRET_VARS,
        )
        self.assertEqual(result.exit_code, 0, result.stderr)
        self.assertTrue(result.stdout.lstrip().startswith("#"), result.stdout[:200])
        self.assertIn("参考文献", result.stdout)
        self.assertNotIn("DeepResearch  v", result.stdout)

    def test_depth_and_language_flags_are_accepted(self) -> None:
        result = run_cli(
            [
                "run",
                "--demo",
                "--stdout",
                "--no-save",
                "--depth",
                "deep",
                "--lang",
                "en",
                "AI chips",
            ],
            env=MOCK_ENV,
            clear_env=SECRET_VARS,
        )
        self.assertEqual(result.exit_code, 0, result.stderr)
        self.assertTrue(result.stdout.strip())

    def test_missing_api_key_is_config_error(self) -> None:
        result = run_cli(
            ["run", "--provider", "openai", "任何问题"],
            env={"DEEPRESEARCH_LLM_PROVIDER": "openai", "DEEPRESEARCH_SEARCH_PROVIDER": "none"},
            clear_env=SECRET_VARS,
        )
        self.assertEqual(result.exit_code, 2)
        self.assertIn("OPENAI_API_KEY", result.stderr)

    def test_invalid_depth_rejected_by_argparse(self) -> None:
        result = run_cli(
            ["run", "问题", "--depth", "infinite"], env=MOCK_ENV, clear_env=SECRET_VARS
        )
        self.assertEqual(result.exit_code, 2)

    def test_question_is_required(self) -> None:
        result = run_cli(["run", "--demo"], env=MOCK_ENV, clear_env=SECRET_VARS)
        self.assertEqual(result.exit_code, 2)


if __name__ == "__main__":
    unittest.main()
