"""Tests for the stdlib HTTP layer."""

from __future__ import annotations

import gzip
import json
import time
import unittest

from deepresearch.http import HttpClient, HttpError, quote_url
from tests.support import LocalServer


class HttpGetTests(unittest.TestCase):
    def test_gets_json_and_decodes_utf8(self) -> None:
        payload = json.dumps({"ok": True, "name": "深度调研"}, ensure_ascii=False)
        with LocalServer(
            {"/api": (200, {"Content-Type": "application/json; charset=utf-8"}, payload)}
        ) as server:
            response = HttpClient(sleeper=lambda _s: None).get(server.url("/api"))
        self.assertTrue(response.ok)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.json()["name"], "深度调研")
        self.assertIn("application/json", response.content_type)

    def test_sends_default_user_agent(self) -> None:
        seen = {}

        def route(method, headers, body):
            seen.update(headers)
            return 200, {"Content-Type": "text/plain"}, "ok"

        with LocalServer({"/ua": route}) as server:
            HttpClient(sleeper=lambda _s: None).get(server.url("/ua"))
        self.assertIn("DeepResearch", seen.get("User-Agent", ""))

    def test_decodes_gzip_body(self) -> None:
        raw = gzip.compress("压缩后的正文".encode("utf-8"))
        with LocalServer(
            {
                "/gz": (
                    200,
                    {"Content-Encoding": "gzip", "Content-Type": "text/plain; charset=utf-8"},
                    raw,
                )
            }
        ) as server:
            response = HttpClient(sleeper=lambda _s: None).get(server.url("/gz"))
        self.assertEqual(response.text, "压缩后的正文")

    def test_404_raises_http_error_with_status(self) -> None:
        with LocalServer({}) as server:
            with self.assertRaises(HttpError) as ctx:
                HttpClient(max_retries=0, sleeper=lambda _s: None).get(server.url("/missing"))
        self.assertEqual(ctx.exception.status, 404)

    def test_retries_transient_errors(self) -> None:
        state = {"calls": 0}

        def flaky(method, headers, body):
            state["calls"] += 1
            if state["calls"] < 3:
                return 503, {"Content-Type": "text/plain"}, "try again"
            return 200, {"Content-Type": "text/plain"}, "finally"

        with LocalServer({"/flaky": flaky}) as server:
            response = HttpClient(max_retries=2, backoff=0.0, sleeper=lambda _s: None).get(
                server.url("/flaky")
            )
        self.assertEqual(response.text, "finally")
        self.assertEqual(state["calls"], 3)

    def test_gives_up_after_retries(self) -> None:
        with LocalServer({"/down": (500, {"Content-Type": "text/plain"}, "boom")}) as server:
            with self.assertRaises(HttpError):
                HttpClient(max_retries=1, backoff=0.0, sleeper=lambda _s: None).get(
                    server.url("/down")
                )

    def test_respects_max_bytes(self) -> None:
        body = "x" * 5000
        with LocalServer({"/big": (200, {"Content-Type": "text/plain"}, body)}) as server:
            response = HttpClient(sleeper=lambda _s: None).get(server.url("/big"), max_bytes=120)
        self.assertLessEqual(len(response.text), 120)

    def test_timeout_is_wrapped(self) -> None:
        def slow(method, headers, body):
            time.sleep(0.4)
            return 200, {"Content-Type": "text/plain"}, "late"

        with LocalServer({"/slow": slow}) as server:
            with self.assertRaises(HttpError):
                HttpClient(max_retries=0, sleeper=lambda _s: None).get(
                    server.url("/slow"), timeout=0.1
                )

    def test_rejects_unsupported_scheme(self) -> None:
        with self.assertRaises(HttpError):
            HttpClient().get("ftp://example.com/x")

    def test_quote_url_keeps_structure(self) -> None:
        self.assertEqual(
            quote_url("https://example.com/路径?q=中文&x=1#片段"),
            "https://example.com/%E8%B7%AF%E5%BE%84?q=%E4%B8%AD%E6%96%87&x=1#%E7%89%87%E6%AE%B5",
        )


class HttpPostTests(unittest.TestCase):
    def test_posts_json_with_headers(self) -> None:
        def echo(method, headers, body):
            record = {
                "method": method,
                "authorization": headers.get("Authorization", ""),
                "payload": json.loads(body or b"{}"),
            }
            return 200, {"Content-Type": "application/json"}, json.dumps(record)

        with LocalServer({"/v1/chat": echo}) as server:
            response = HttpClient(sleeper=lambda _s: None).post_json(
                server.url("/v1/chat"),
                {"model": "test-model", "messages": [{"role": "user", "content": "你好"}]},
                headers={"Authorization": "Bearer sk-test"},
            )
        record = response.json()
        self.assertEqual(record["method"], "POST")
        self.assertEqual(record["authorization"], "Bearer sk-test")
        self.assertEqual(record["payload"]["messages"][0]["content"], "你好")


if __name__ == "__main__":
    unittest.main()
