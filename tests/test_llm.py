"""Tests for the LLM providers — fully offline, no real network.

``OpenAICompatLLM`` is exercised against ``tests.support.LocalServer`` so the
request body, auth header, JSON parsing, retries and error mapping can be
asserted exactly.  ``MockLLM`` is checked against the prompt contract from
CONTRACTS.md §5.3 / §7 and must stay deterministic.
"""

from __future__ import annotations

import json
import re
import unittest
from typing import Any, Dict, List, Union

from deepresearch.config import Settings
from deepresearch.errors import ConfigError, LLMError
from deepresearch.http import HttpClient
from deepresearch.llm import MockLLM, OpenAICompatLLM, build_llm
from deepresearch.llm.base import Message
from tests.support import LocalServer, mock_settings

SECRET = "sk-test-secret"

COMPLETION: Dict[str, Any] = {
    "id": "chatcmpl-test",
    "model": "test-model-2025",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Hello 世界"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
}


def _http(**overrides: Any) -> HttpClient:
    """HttpClient with instant retries (no real sleeping in tests)."""
    options: Dict[str, Any] = {"timeout": 5.0, "backoff": 0.0, "sleeper": lambda _s: None}
    options.update(overrides)
    return HttpClient(**options)


def _settings(base_url: str = "", **overrides: Any) -> Settings:
    values: Dict[str, Any] = {
        "llm_provider": "openai",
        "llm_model": "test-model",
        "llm_api_key": SECRET,
        "llm_base_url": base_url or "http://127.0.0.1:9/v1",
    }
    values.update(overrides)
    settings = Settings(**values)
    settings._apply_preset_defaults()
    return settings


def _completion_route(captured: Dict[str, Any]):
    def route(method: str, headers: Dict[str, str], body: bytes) -> Any:
        captured["method"] = method
        captured["headers"] = {key.lower(): value for key, value in headers.items()}
        captured["body"] = json.loads(body.decode("utf-8")) if body else {}
        return 200, {"Content-Type": "application/json"}, json.dumps(COMPLETION).encode()

    return route


def _chat_route(completion: Dict[str, Any] = COMPLETION):
    payload = json.dumps(completion).encode("utf-8")
    return lambda _method, _headers, _body: (200, {"Content-Type": "application/json"}, payload)


class OpenAICompatLLMTests(unittest.TestCase):
    def test_request_headers_body_and_usage(self) -> None:
        captured: Dict[str, Any] = {}
        with LocalServer({"/v1/chat/completions": _completion_route(captured)}) as server:
            llm = OpenAICompatLLM(_settings(server.url("/v1")), http=_http())
            response = llm.complete([Message(role="user", content="hi there")])

        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["headers"].get("authorization"), f"Bearer {SECRET}")
        self.assertTrue(captured["headers"].get("content-type", "").startswith("application/json"))
        payload = captured["body"]
        self.assertEqual(payload["model"], "test-model")
        self.assertEqual(payload["messages"], [{"role": "user", "content": "hi there"}])
        self.assertFalse(payload["stream"])
        self.assertAlmostEqual(payload["temperature"], 0.3)
        self.assertNotIn("response_format", payload)
        self.assertNotIn("max_tokens", payload)

        self.assertEqual(response.text, "Hello 世界")
        self.assertEqual(response.prompt_tokens, 11)
        self.assertEqual(response.completion_tokens, 7)
        self.assertEqual(response.total_tokens, 18)
        self.assertEqual(response.finish_reason, "stop")
        self.assertGreaterEqual(response.latency_s, 0.0)
        self.assertEqual(llm.name, "openai-compat/test-model")

    def test_json_mode_sets_response_format(self) -> None:
        captured: Dict[str, Any] = {}
        with LocalServer({"/v1/chat/completions": _completion_route(captured)}) as server:
            llm = OpenAICompatLLM(_settings(server.url("/v1")), http=_http())
            llm.complete([Message(role="user", content="json")], json_mode=True)
        self.assertEqual(captured["body"]["response_format"], {"type": "json_object"})

    def test_max_tokens_argument_overrides_settings(self) -> None:
        captured: Dict[str, Any] = {}
        with LocalServer({"/v1/chat/completions": _completion_route(captured)}) as server:
            settings = _settings(server.url("/v1"), llm_max_tokens=128)
            llm = OpenAICompatLLM(settings, http=_http())
            llm.complete([Message(role="user", content="a")])
            self.assertEqual(captured["body"]["max_tokens"], 128)
            llm.complete([Message(role="user", content="b")], max_tokens=64)
            self.assertEqual(captured["body"]["max_tokens"], 64)

    def test_429_is_retried_by_http_client(self) -> None:
        calls = {"count": 0}

        def route(_method: str, _headers: Dict[str, str], _body: bytes) -> Any:
            calls["count"] += 1
            if calls["count"] == 1:
                return 429, {"Content-Type": "application/json"}, b'{"error": "rate limited"}'
            return 200, {"Content-Type": "application/json"}, json.dumps(COMPLETION).encode()

        with LocalServer({"/v1/chat/completions": route}) as server:
            llm = OpenAICompatLLM(_settings(server.url("/v1")), http=_http(max_retries=2))
            response = llm.complete([Message(role="user", content="retry please")])

        self.assertEqual(calls["count"], 2)
        self.assertEqual(response.text, "Hello 世界")

    def test_server_error_maps_to_llm_error(self) -> None:
        body = b'{"error": {"message": "upstream exploded", "type": "server_error"}}'
        def route(_m, _h, _b):
            return (500, {"Content-Type": "application/json"}, body)
        with LocalServer({"/v1/chat/completions": route}) as server:
            llm = OpenAICompatLLM(_settings(server.url("/v1")), http=_http(max_retries=0))
            with self.assertRaises(LLMError) as ctx:
                llm.complete([Message(role="user", content="boom")])
        message = str(ctx.exception)
        self.assertIn("500", message)
        self.assertIn("upstream exploded", message)

    def test_error_message_never_leaks_api_key(self) -> None:
        body = json.dumps({"error": {"message": f"invalid api key {SECRET}"}}).encode()
        def route(_m, _h, _b):
            return (401, {"Content-Type": "application/json"}, body)
        with LocalServer({"/v1/chat/completions": route}) as server:
            llm = OpenAICompatLLM(_settings(server.url("/v1")), http=_http(max_retries=0))
            with self.assertRaises(LLMError) as ctx:
                llm.complete([Message(role="user", content="auth")])
        message = str(ctx.exception)
        self.assertIn("401", message)
        self.assertNotIn(SECRET, message)

    def test_invalid_response_bodies_raise_llm_error(self) -> None:
        bodies = [
            b"not-json-at-all",
            b'{"choices": []}',
            b'{"choices": [{"message": {"content": ""}}]}',
            b"[]",
        ]
        for body in bodies:
            with self.subTest(body=body):
                def route(_m, _h, _b, payload=body):
                    return (
                                    200,
                                    {"Content-Type": "application/json"},
                                    payload,
                                )
                with LocalServer({"/v1/chat/completions": route}) as server:
                    llm = OpenAICompatLLM(_settings(server.url("/v1")), http=_http(max_retries=0))
                    with self.assertRaises(LLMError):
                        llm.complete([Message(role="user", content="x")])

    def test_content_parts_are_joined(self) -> None:
        completion = dict(COMPLETION)
        completion["choices"] = [
            {
                "message": {
                    "content": [{"type": "text", "text": "part one "}, {"text": "part two"}]
                },
                "finish_reason": "stop",
            }
        ]
        with LocalServer({"/v1/chat/completions": _chat_route(completion)}) as server:
            llm = OpenAICompatLLM(_settings(server.url("/v1")), http=_http())
            self.assertEqual(
                llm.complete([Message(role="user", content="x")]).text,
                "part one part two",
            )

    def test_factory_mapping(self) -> None:
        self.assertIsInstance(build_llm(mock_settings()), MockLLM)
        self.assertIsInstance(build_llm(_settings()), OpenAICompatLLM)
        for provider in ("deepseek", "openai", "openrouter", "custom"):
            with self.subTest(provider=provider):
                settings = Settings(
                    llm_provider=provider,
                    llm_model="m",
                    llm_api_key=SECRET,
                    llm_base_url="https://example.invalid/v1",
                )
                self.assertIsInstance(build_llm(settings), OpenAICompatLLM)
        ollama = Settings(llm_provider="ollama")
        ollama._apply_preset_defaults()
        self.assertIsInstance(build_llm(ollama), OpenAICompatLLM)

    def test_factory_config_errors(self) -> None:
        with self.assertRaises(ConfigError):
            build_llm(_settings(llm_api_key=""))
        with self.assertRaises(ConfigError):
            build_llm(Settings(llm_provider="mystery-provider"))
        with self.assertRaises(ConfigError):
            build_llm(Settings(llm_provider="openai", llm_api_key=SECRET, llm_base_url=""))


# --------------------------------------------------------------------------- #
# MockLLM — prompt contract and determinism
# --------------------------------------------------------------------------- #
QUESTION = "固态电池 2025 年产业化进展"


def _plan_prompt(
    question: str = QUESTION,
    *,
    language: str = "zh",
    max_sub_questions: int = 5,
    queries_per_question: int = 3,
) -> List[Message]:
    user = "\n".join(
        [
            "TASK: plan",
            f"LANGUAGE: {language}",
            "DEPTH: standard",
            f"QUESTION: {question}",
            f"MAX_SUB_QUESTIONS: {max_sub_questions}",
            f"QUERIES_PER_QUESTION: {queries_per_question}",
        ]
    )
    return [
        Message(role="system", content="You are a researcher. Output JSON only."),
        Message(role="user", content=user),
    ]


def _findings_prompt(
    question: str = QUESTION,
    *,
    qid: str = "Q2",
    source_ids: Union[List[str], None] = None,
) -> List[Message]:
    source_ids = source_ids or ["S1", "S2", "S3"]
    lines = [
        "TASK: findings",
        "LANGUAGE: zh",
        f"QUESTION: {question}",
        "ROUND: 1",
        f"SUB_QUESTION: {qid} — {question}的最新进展与关键数据是什么？",
        "SOURCES:",
    ]
    for index, sid in enumerate(source_ids, 1):
        lines.append(f"[{sid}] 来源{index}标题 | https://example.com/{index}")
        lines.append(f"来源 {sid} 的正文摘要：样本量 {100 + index}，同比增长 18.4%。")
    return [Message(role="user", content="\n".join(lines))]


def _outline_prompt(question: str = QUESTION, *, structure: bool = True) -> List[Message]:
    lines = [
        "TASK: outline",
        "LANGUAGE: zh",
        f"QUESTION: {question}",
        "MAX_SECTIONS: 5",
        "SOURCES:",
        "[S1] 来源一 | https://example.com/1",
        "[S2] 来源二 | https://example.com/2",
        "[S3] 来源三 | https://example.com/3",
        "FINDINGS:",
        "[F1] Q1 | 背景证据 [S1]",
        "[F2] Q2 | 进展证据 [S2]",
        "[F3] Q3 | 风险证据 [S3]",
    ]
    if structure:
        lines = (
            lines[:4]
            + [
                "SUB_QUESTIONS:",
                "Q1 | 核心背景与现状",
                "Q2 | 最新进展与数据",
                "Q3 | 风险与瓶颈",
            ]
            + lines[4:]
        )
    return [Message(role="user", content="\n".join(lines))]


def _section_prompt(*, heading: str = "最新进展与关键数据", source_ids=None) -> List[Message]:
    source_ids = source_ids or ["S1", "S2"]
    lines = [
        "TASK: section",
        "LANGUAGE: zh",
        f"QUESTION: {QUESTION}",
        f"SECTION: {heading}",
        "BRIEF: 梳理最新进展与关键数字。",
        "SOURCES:",
    ]
    for index, sid in enumerate(source_ids, 1):
        lines.append(f"[{sid}] 来源{index}标题 | https://example.com/{index}")
        lines.append(f"来源 {sid} 的正文摘要：样本量 {100 + index}，同比增长 18.4%。")
    return [Message(role="user", content="\n".join(lines))]


def _meta_prompt() -> List[Message]:
    user = "\n".join(
        [
            "TASK: meta",
            "LANGUAGE: zh",
            f"QUESTION: {QUESTION}",
            "SECTIONS:",
            "1. 研究背景与问题界定",
            "2. 最新进展与关键数据",
            "3. 风险、争议与瓶颈",
            "SOURCES:",
            "[S1] 来源一 | https://example.com/1",
            "[S2] 来源二 | https://example.com/2",
        ]
    )
    return [Message(role="user", content=user)]


def _json_response(llm: MockLLM, messages: List[Message]) -> Dict[str, Any]:
    response = llm.complete(messages, json_mode=True)
    return json.loads(response.text)


class MockLLMTests(unittest.TestCase):
    def setUp(self) -> None:
        self.llm = MockLLM()

    def test_name_and_zero_latency(self) -> None:
        self.assertEqual(self.llm.name, "mock")
        response = self.llm.complete(_plan_prompt())
        self.assertGreaterEqual(response.latency_s, 0.0)
        self.assertGreater(response.prompt_tokens, 0)
        self.assertGreater(response.completion_tokens, 0)

    # -- plan -------------------------------------------------------------- #
    def test_plan_schema(self) -> None:
        data = _json_response(self.llm, _plan_prompt())
        self.assertEqual(set(data), {"search_strategy", "sub_questions"})
        self.assertTrue(data["search_strategy"])
        sub_questions = data["sub_questions"]
        self.assertEqual(len(sub_questions), 5)
        for index, item in enumerate(sub_questions, 1):
            self.assertEqual(set(item), {"question", "rationale", "queries", "priority"})
            self.assertTrue(item["question"])
            self.assertTrue(item["rationale"])
            self.assertIsInstance(item["priority"], int)
            self.assertEqual(item["priority"], index)
            self.assertGreaterEqual(len(item["queries"]), 2)
            self.assertLessEqual(len(item["queries"]), 4)
            self.assertTrue(all(isinstance(query, str) and query for query in item["queries"]))
        self.assertIn(QUESTION, sub_questions[0]["question"])

    def test_plan_respects_max_sub_questions_and_language(self) -> None:
        data = _json_response(self.llm, _plan_prompt(max_sub_questions=3))
        self.assertEqual(len(data["sub_questions"]), 3)
        english = _json_response(
            self.llm, _plan_prompt("solid-state battery industrialization", language="en")
        )
        self.assertIn("What", english["sub_questions"][0]["question"])

    def test_plan_is_deterministic(self) -> None:
        first = self.llm.complete(_plan_prompt()).text
        second = self.llm.complete(_plan_prompt()).text
        self.assertEqual(first, second)

    # -- findings ---------------------------------------------------------- #
    def test_findings_schema_and_legal_citations(self) -> None:
        data = _json_response(self.llm, _findings_prompt())
        self.assertEqual(set(data), {"findings", "gaps"})
        findings = data["findings"]
        self.assertGreaterEqual(len(findings), 1)
        self.assertLessEqual(len(findings), 2)
        for finding in findings:
            self.assertEqual(finding["sub_question_id"], "Q2")
            self.assertIsInstance(finding["claim"], str)
            self.assertRegex(finding["claim"], r"\d")
            self.assertIsInstance(finding["evidence"], str)
            self.assertTrue(finding["source_ids"])
            self.assertTrue(set(finding["source_ids"]) <= {"S1", "S2", "S3"})
            self.assertGreaterEqual(finding["confidence"], 0.0)
            self.assertLessEqual(finding["confidence"], 1.0)
        gaps = data["gaps"]
        self.assertGreaterEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["sub_question_id"], "Q2")
        self.assertTrue(gaps[0]["queries"])

    def test_findings_fallbacks_without_sources(self) -> None:
        prompt = [Message(role="user", content="TASK: findings\nLANGUAGE: zh\nQUESTION: 测试问题")]
        data = _json_response(self.llm, prompt)
        self.assertEqual(data["findings"][0]["sub_question_id"], "Q1")
        self.assertEqual(data["findings"][0]["source_ids"], ["S1"])

    def test_findings_are_deterministic(self) -> None:
        self.assertEqual(
            self.llm.complete(_findings_prompt()).text,
            self.llm.complete(_findings_prompt()).text,
        )

    # -- outline ----------------------------------------------------------- #
    def test_outline_schema_and_references(self) -> None:
        data = _json_response(self.llm, _outline_prompt())
        self.assertEqual(set(data), {"title", "summary", "key_takeaways", "sections"})
        self.assertTrue(data["title"])
        self.assertTrue(data["summary"])
        self.assertGreaterEqual(len(data["key_takeaways"]), 3)
        sections = data["sections"]
        self.assertEqual(len(sections), 3)
        prompt_qids = {"Q1", "Q2", "Q3"}
        prompt_sids = {"S1", "S2", "S3"}
        for section in sections:
            self.assertTrue(section["heading"])
            self.assertTrue(section["brief"])
            self.assertTrue(set(section["sub_question_ids"]) <= prompt_qids)
            self.assertTrue(set(section["source_ids"]) <= prompt_sids)
        self.assertEqual(
            [section["sub_question_ids"] for section in sections],
            [["Q1"], ["Q2"], ["Q3"]],
        )
        self.assertEqual(
            self.llm.complete(_outline_prompt()).text,
            self.llm.complete(_outline_prompt()).text,
        )

    def test_outline_handles_levels_sections(self) -> None:
        data = _json_response(self.llm, _outline_prompt(structure=False))
        self.assertGreaterEqual(len(data["sections"]), 3)
        self.assertTrue(all(section["heading"] for section in data["sections"]))

    # -- section ----------------------------------------------------------- #
    def test_section_heading_body_and_citations(self) -> None:
        data = _json_response(self.llm, _section_prompt())
        self.assertEqual(set(data), {"heading", "body_md"})
        self.assertEqual(data["heading"], "最新进展与关键数据")
        body = data["body_md"]
        self.assertIn("[S1]", body)
        self.assertIn("[S2]", body)
        self.assertNotIn("S3", body)
        cjk = len(re.findall(r"[\u4e00-\u9fff]", body))
        self.assertGreaterEqual(cjk, 200)
        self.assertLessEqual(cjk, 450)
        self.assertGreaterEqual(len(body), 250)

    def test_section_default_heading(self) -> None:
        prompt = [Message(role="user", content="TASK: section\nLANGUAGE: zh\nQUESTION: 测试")]
        data = _json_response(self.llm, prompt)
        self.assertTrue(data["heading"])
        self.assertIn("[S1]", data["body_md"])

    def test_section_is_deterministic(self) -> None:
        self.assertEqual(
            self.llm.complete(_section_prompt()).text,
            self.llm.complete(_section_prompt()).text,
        )

    # -- meta -------------------------------------------------------------- #
    def test_meta_schema(self) -> None:
        data = _json_response(self.llm, _meta_prompt())
        self.assertEqual(set(data), {"title", "summary", "key_takeaways", "limitations"})
        self.assertTrue(data["title"])
        self.assertTrue(data["summary"])
        self.assertGreaterEqual(len(data["key_takeaways"]), 3)
        self.assertGreaterEqual(len(data["limitations"]), 2)
        heading_mentions = "、".join(data["key_takeaways"]) + data["summary"]
        self.assertIn("研究背景与问题界定", heading_mentions)
        self.assertEqual(
            self.llm.complete(_meta_prompt()).text,
            self.llm.complete(_meta_prompt()).text,
        )

    def test_unknown_task_returns_prose(self) -> None:
        prompt = [Message(role="user", content="TASK: chitchat\nQUESTION: 你好")]
        response = self.llm.complete(prompt)
        self.assertFalse(response.text.lstrip().startswith("{"))
        self.assertIn("MockLLM", response.text)

    def test_optional_latency_argument(self) -> None:
        llm = MockLLM(0.001)
        response = llm.complete(_plan_prompt())
        self.assertGreaterEqual(response.latency_s, 0.001)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
