"""Tests for configuration resolution, presets and validation."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from deepresearch.config import PRESETS, Settings, load_dotenv
from deepresearch.errors import ConfigError
from tests.support import temp_workspace


def isolated_env(**values: str) -> dict:
    """A fake environment that only contains ``values`` (no ambient keys)."""
    return dict(values)


class SettingsDefaultsTests(unittest.TestCase):
    def test_defaults_are_fully_offline(self) -> None:
        settings = Settings()
        self.assertEqual(settings.llm_provider, "mock")
        self.assertEqual(settings.search_provider, "mock")
        self.assertEqual(settings.depth, "standard")
        self.assertEqual(settings.language, "zh")
        self.assertEqual(settings.validate(), [])

    def test_from_env_without_anything_is_offline(self) -> None:
        settings = Settings.from_env(env_file=None, environ=isolated_env())
        self.assertEqual(settings.llm_provider, "mock")
        self.assertEqual(settings.search_provider, "mock")
        self.assertEqual(settings.llm_model, "mock-researcher")

    def test_profile_limits(self) -> None:
        self.assertEqual(Settings().profile().max_sub_questions, 5)
        quick = Settings.from_env(env_file=None, environ=isolated_env(DEEPRESEARCH_DEPTH="quick"))
        self.assertEqual(quick.depth, "quick")
        self.assertEqual(quick.profile().max_sources, 8)
        deep = quick.with_overrides(depth="deep")
        self.assertEqual(deep.profile().max_sources, 24)

    def test_max_sources_overrides_profile(self) -> None:
        settings = Settings.from_env(
            env_file=None, environ=isolated_env(DEEPRESEARCH_MAX_SOURCES="3")
        )
        self.assertEqual(settings.profile().max_sources, 3)


class ProviderDetectionTests(unittest.TestCase):
    def test_detects_deepseek_from_api_key(self) -> None:
        settings = Settings.from_env(env_file=None, environ=isolated_env(DEEPSEEK_API_KEY="sk-abc"))
        self.assertEqual(settings.llm_provider, "deepseek")
        self.assertEqual(settings.llm_base_url, PRESETS["deepseek"]["base_url"])
        self.assertEqual(settings.llm_model, "deepseek-chat")
        self.assertEqual(settings.llm_api_key, "sk-abc")
        # No search backend configured -> knowledge-only mode is a warning, not an error.
        warnings = settings.validate()
        self.assertEqual(len(warnings), 1)
        self.assertIn("no web search", warnings[0])

    def test_detects_openai_from_api_key(self) -> None:
        settings = Settings.from_env(
            env_file=None, environ=isolated_env(OPENAI_API_KEY="sk-openai")
        )
        self.assertEqual(settings.llm_provider, "openai")
        self.assertEqual(settings.llm_model, "gpt-4o-mini")

    def test_explicit_provider_wins(self) -> None:
        settings = Settings.from_env(
            env_file=None,
            environ=isolated_env(DEEPSEEK_API_KEY="sk-abc", OPENAI_API_KEY="sk-def"),
        )
        self.assertEqual(settings.llm_provider, "deepseek")
        settings = Settings.from_env(
            env_file=None,
            environ=isolated_env(DEEPRESEARCH_LLM_PROVIDER="openai", OPENAI_API_KEY="sk-def"),
        )
        self.assertEqual(settings.llm_provider, "openai")

    def test_missing_key_raises_actionable_error(self) -> None:
        settings = Settings.from_env(
            env_file=None, environ=isolated_env(DEEPRESEARCH_LLM_PROVIDER="openai")
        )
        with self.assertRaises(ConfigError) as ctx:
            settings.validate()
        self.assertIn("OPENAI_API_KEY", str(ctx.exception))

    def test_tavily_detected_and_requires_key(self) -> None:
        settings = Settings.from_env(
            env_file=None, environ=isolated_env(DEEPSEEK_API_KEY="sk-abc", TAVILY_API_KEY="tvly-1")
        )
        self.assertEqual(settings.search_provider, "tavily")
        self.assertEqual(settings.validate(), [])
        broken = Settings.from_env(
            env_file=None, environ=isolated_env(DEEPRESEARCH_SEARCH_PROVIDER="tavily")
        )
        with self.assertRaises(ConfigError):
            broken.validate()

    def test_searxng_requires_url(self) -> None:
        settings = Settings.from_env(
            env_file=None, environ=isolated_env(DEEPRESEARCH_SEARCH_PROVIDER="searxng")
        )
        with self.assertRaises(ConfigError):
            settings.validate()

    def test_search_none_is_a_warning_not_an_error(self) -> None:
        settings = Settings.from_env(
            env_file=None,
            environ=isolated_env(DEEPSEEK_API_KEY="sk-abc", DEEPRESEARCH_SEARCH_PROVIDER="none"),
        )
        warnings = settings.validate()
        self.assertEqual(len(warnings), 1)
        self.assertIn("web search", warnings[0])

    def test_custom_provider_requires_endpoint_and_model(self) -> None:
        settings = Settings.from_env(
            env_file=None,
            environ=isolated_env(
                DEEPRESEARCH_LLM_PROVIDER="custom",
                DEEPRESEARCH_LLM_API_KEY="k",
                DEEPRESEARCH_LLM_BASE_URL="http://localhost:8000/v1",
                DEEPRESEARCH_LLM_MODEL="m",
                DEEPRESEARCH_SEARCH_PROVIDER="none",
            ),
        )
        self.assertEqual(len(settings.validate()), 1)  # knowledge-only warning
        broken = settings.with_overrides(llm_model="")
        with self.assertRaises(ConfigError):
            broken.validate()

    def test_unknown_provider_rejected(self) -> None:
        with self.assertRaises(ConfigError):
            Settings.from_env(
                env_file=None,
                environ=isolated_env(DEEPRESEARCH_LLM_PROVIDER="not-a-provider"),
            )


class EnvParsingTests(unittest.TestCase):
    def test_coerces_types(self) -> None:
        settings = Settings.from_env(
            env_file=None,
            environ=isolated_env(
                DEEPRESEARCH_LLM_TEMPERATURE="0.7",
                DEEPRESEARCH_FETCH_CONCURRENCY="8",
                DEEPRESEARCH_USE_CACHE="false",
                DEEPRESEARCH_SEARCH_MAX_RESULTS="99",
            ),
        )
        self.assertAlmostEqual(settings.llm_temperature, 0.7)
        self.assertEqual(settings.fetch_concurrency, 8)
        self.assertFalse(settings.use_cache)
        self.assertEqual(settings.search_max_results, 20)  # clamped

    def test_invalid_number_raises(self) -> None:
        with self.assertRaises(ConfigError):
            Settings.from_env(
                env_file=None, environ=isolated_env(DEEPRESEARCH_LLM_TEMPERATURE="hot")
            )

    def test_unknown_override_rejected(self) -> None:
        with self.assertRaises(ConfigError):
            Settings.from_env(env_file=None, environ=isolated_env(), nonsense=1)

    def test_invalid_depth_rejected(self) -> None:
        with self.assertRaises(ConfigError):
            Settings.from_env(env_file=None, environ=isolated_env(DEEPRESEARCH_DEPTH="infinite"))

    def test_language_normalised(self) -> None:
        settings = Settings.from_env(
            env_file=None, environ=isolated_env(DEEPRESEARCH_LANGUAGE="en-US")
        )
        self.assertEqual(settings.language, "en")
        settings = Settings.from_env(
            env_file=None, environ=isolated_env(DEEPRESEARCH_LANGUAGE="fr")
        )
        self.assertEqual(settings.language, "zh")

    def test_env_file_loading(self) -> None:
        with temp_workspace() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "# comment\n"
                "export DEEPRESEARCH_LLM_PROVIDER=deepseek\n"
                'DEEPSEEK_API_KEY="sk-quoted"\n'
                "DEEPRESEARCH_OUT_DIR=./out  # inline comment\n"
                "DEEPRESEARCH_LANGUAGE=zh\n",
                encoding="utf-8",
            )
            values = load_dotenv(env_path)
        self.assertEqual(values["DEEPRESEARCH_LLM_PROVIDER"], "deepseek")
        self.assertEqual(values["DEEPSEEK_API_KEY"], "sk-quoted")
        self.assertEqual(values["DEEPRESEARCH_OUT_DIR"], "./out")

    def test_load_dotenv_expands_variables(self) -> None:
        os.environ.setdefault("DEEPRESEARCH_TEST_ROOT", "/tmp/root")
        with temp_workspace() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "DEEPRESEARCH_CACHE_DIR=${DEEPRESEARCH_TEST_ROOT}/cache\n", encoding="utf-8"
            )
            values = load_dotenv(env_path)
        self.assertEqual(values["DEEPRESEARCH_CACHE_DIR"], "/tmp/root/cache")

    def test_load_dotenv_missing_file(self) -> None:
        self.assertEqual(load_dotenv("does-not-exist.env"), {})


class HelpersTests(unittest.TestCase):
    def test_public_dict_masks_secrets(self) -> None:
        settings = Settings.from_env(
            env_file=None,
            environ=isolated_env(
                DEEPSEEK_API_KEY="sk-1234567890abcdef", TAVILY_API_KEY="tvly-abcdef123456"
            ),
        )
        public = settings.public_dict()
        self.assertNotIn("1234567890abcdef", str(public))
        self.assertTrue(public["llm_api_key"].startswith("sk-1"))
        self.assertTrue(public["llm_api_key"].endswith("cdef"))
        self.assertFalse(public["offline"])

    def test_estimate_cost(self) -> None:
        settings = Settings.from_env(
            env_file=None, environ=isolated_env(DEEPRESEARCH_LLM_PROVIDER="mock")
        )
        settings = settings.with_overrides(llm_provider="openai", llm_model="gpt-4o-mini")
        cost = settings.estimate_cost(1_000_000, 1_000_000)
        self.assertAlmostEqual(cost, 0.75)

    def test_describe_contains_key_rows(self) -> None:
        labels = {label for label, _ in Settings().describe()}
        self.assertIn("LLM provider", labels)
        self.assertIn("Search provider", labels)


if __name__ == "__main__":
    unittest.main()
