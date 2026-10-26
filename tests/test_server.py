"""Integration tests for the DeepResearch stdlib web server.

The whole suite runs against a real ``ThreadingHTTPServer`` bound to an
ephemeral port with fully mocked providers (``mock_settings()``), so it never
touches the network and stays fast.  ``post_sse_events`` from
``tests/support.py`` collects the Server-Sent Events of a complete run.
"""

from __future__ import annotations

import json
import threading
import time
import unittest
import urllib.error
import urllib.request

from deepresearch.server import create_server
from tests.support import http_json, http_text, mock_settings, post_sse_events

STARTUP_TIMEOUT = 5.0
QUESTION = "固态电池 2025 年产业化进展"


class ServerTestCase(unittest.TestCase):
    """One server instance shared by the read-only tests in this module."""

    settings = None
    httpd = None
    thread = None
    base = ""
    _run_cache = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = mock_settings()
        cls.httpd = create_server(cls.settings, "127.0.0.1", 0)
        port = int(cls.httpd.server_address[1])
        cls.base = f"http://127.0.0.1:{port}"
        cls.thread = threading.Thread(
            target=cls.httpd.serve_forever, name="test-web-server", daemon=True
        )
        cls.thread.start()
        cls._wait_until_ready()

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.httpd is not None:
            cls.httpd.shutdown()
            cls.httpd.server_close()
        if cls.thread is not None:
            cls.thread.join(timeout=5)

    @classmethod
    def _wait_until_ready(cls) -> None:
        deadline = time.time() + STARTUP_TIMEOUT
        while time.time() < deadline:
            try:
                http_json(cls.base + "/api/health", timeout=1.0)
                return
            except Exception:  # noqa: BLE001 - server not accepting yet
                time.sleep(0.05)
        raise RuntimeError("web server did not start in time")

    # -- helpers ------------------------------------------------------- #
    def _post_raw(self, path: str, data: bytes, content_type: str = "application/json"):
        request = urllib.request.Request(
            self.base + path,
            data=data,
            headers={"Content-Type": content_type},
            method="POST",
        )
        return urllib.request.urlopen(request, timeout=15)

    def _post_error(self, path: str, data: bytes) -> tuple[int, str, str]:
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self._post_raw(path, data)
        error = caught.exception
        try:
            body = error.read().decode("utf-8")
            return int(error.code), error.headers.get("Content-Type", ""), body
        finally:
            error.close()

    def _ensure_run(self):
        """Run the mock pipeline once over SSE and cache the parsed stream."""
        if self.__class__._run_cache is None:
            self.__class__._run_cache = post_sse_events(
                self.base + "/api/research", {"question": QUESTION, "depth": "quick"}
            )
        return self.__class__._run_cache

    # -- health / config ----------------------------------------------- #
    def test_server_health(self) -> None:
        payload = http_json(self.base + "/api/health")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["version"], "0.1.0")
        self.assertIs(payload["offline"], True)

    def test_server_config_is_public_and_masked(self) -> None:
        config = http_json(self.base + "/api/config")
        self.assertEqual(config["llm_provider"], "mock")
        self.assertEqual(config["search_provider"], "mock")
        self.assertIs(config["offline"], True)
        self.assertIn("llm_model", config)
        self.assertIn("out_dir", config)
        # public_dict() masks secrets; the mock stack carries no key at all.
        self.assertEqual(config["llm_api_key"], "")

    # -- static assets -------------------------------------------------- #
    def test_server_index_page(self) -> None:
        status, content_type, body = http_text(self.base + "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn("DeepResearch", body)
        self.assertIn("/static/style.css", body)
        self.assertIn("/static/app.js", body)
        # No external resources: the UI must work fully offline.
        self.assertNotIn("cdn.", body)
        self.assertNotIn("https://fonts.", body)

    def test_server_static_assets(self) -> None:
        for path, expected_type in (
            ("/static/style.css", "text/css"),
            ("/static/app.js", "javascript"),
        ):
            with self.subTest(path=path):
                status, content_type, body = http_text(self.base + path)
                self.assertEqual(status, 200)
                self.assertIn(expected_type, content_type)
                self.assertGreater(len(body), 500)

    def test_server_static_directory_traversal_is_blocked(self) -> None:
        for path in (
            "/static/../pyproject.toml",
            "/static/%2e%2e/pyproject.toml",
            "/static/..%5cREADME.md",
            "/static/C:/Windows/win.ini",
        ):
            with self.subTest(path=path):
                status, content_type, _body = http_text(self.base + path)
                self.assertEqual(status, 404)
                self.assertIn("application/json", content_type)

    # -- request validation --------------------------------------------- #
    def test_server_missing_question_returns_400(self) -> None:
        for payload in ({}, {"question": ""}, {"question": "   "}, {"question": 42}):
            with self.subTest(payload=payload):
                code, content_type, body = self._post_error(
                    "/api/research", json.dumps(payload).encode("utf-8")
                )
                self.assertEqual(code, 400)
                self.assertIn("application/json", content_type)
                data = json.loads(body)
                self.assertFalse(data["ok"])
                self.assertIn("question", data["error"])

    def test_server_invalid_json_returns_400(self) -> None:
        code, content_type, _body = self._post_error("/api/research", b"{not-json")
        self.assertEqual(code, 400)
        self.assertIn("application/json", content_type)

    def test_server_invalid_depth_returns_400(self) -> None:
        payload = {"question": QUESTION, "depth": "ultra"}
        code, _content_type, body = self._post_error(
            "/api/research", json.dumps(payload).encode("utf-8")
        )
        self.assertEqual(code, 400)
        self.assertIn("depth", body.lower())

    def test_server_oversized_body_returns_413(self) -> None:
        payload = {"question": "x" * 9000}
        code, content_type, _body = self._post_error(
            "/api/research", json.dumps(payload).encode("utf-8")
        )
        self.assertEqual(code, 413)
        self.assertIn("application/json", content_type)

    def test_server_unknown_route_returns_404(self) -> None:
        status, content_type, _body = http_text(self.base + "/api/nope")
        self.assertEqual(status, 404)
        self.assertIn("application/json", content_type)

    # -- SSE research ---------------------------------------------------- #
    def test_server_research_streams_progress_and_result(self) -> None:
        status, content_type, events = self._ensure_run()
        self.assertEqual(status, 200)
        self.assertIn("text/event-stream", content_type)
        self.assertGreaterEqual(len(events), 4)

        progress = [event for event in events if event.get("event") == "progress"]
        self.assertGreaterEqual(len(progress), 3)
        progress_types = []
        for event in progress:
            data = json.loads(event["data"])
            self.assertIn("type", data)
            self.assertIn("message", data)
            self.assertIn("percent", data)
            progress_types.append(data["type"])
        self.assertIn("run_start", progress_types)
        self.assertIn("report_ready", progress_types)

        self.assertEqual(events[-1].get("event"), "result")
        result = json.loads(events[-1]["data"])
        self.assertTrue(result["run_id"])
        self.assertTrue(result["title"])
        self.assertIn("参考文献", result["markdown"])
        self.assertIn("summary", result)
        self.assertIsInstance(result["usage"], dict)
        self.assertGreaterEqual(result["source_count"], 1)
        self.assertEqual(result["report_url"], f"/api/runs/{result['run_id']}/report.md")

    # -- run registry + downloads ---------------------------------------- #
    def test_server_runs_list_and_downloads(self) -> None:
        _status, _content_type, events = self._ensure_run()
        result = json.loads(events[-1]["data"])
        run_id = result["run_id"]

        status, content_type, raw = http_text(self.base + "/api/runs")
        self.assertEqual(status, 200)
        self.assertIn("application/json", content_type)
        self.assertIn(QUESTION, raw)  # ensure_ascii=False on the wire
        runs = json.loads(raw)["runs"]
        self.assertGreaterEqual(len(runs), 1)
        ids = [run["id"] for run in runs]
        self.assertIn(run_id, ids)
        record = next(run for run in runs if run["id"] == run_id)
        for key in ("id", "question", "title", "created_at", "markdown_path"):
            self.assertIn(key, record)

        report_status, report_type, markdown = http_text(
            self.base + f"/api/runs/{run_id}/report.md"
        )
        self.assertEqual(report_status, 200)
        self.assertIn("text/markdown", report_type)
        self.assertIn("参考文献", markdown)
        self.assertEqual(markdown, result["markdown"])

        status, content_type, body = http_text(self.base + f"/api/runs/{run_id}/result.json")
        self.assertEqual(status, 200)
        self.assertIn("application/json", content_type)
        payload = json.loads(body)
        self.assertEqual(payload["run_id"], run_id)
        self.assertIn("markdown", payload)
        self.assertIn("report", payload)

    def test_server_unknown_run_returns_404(self) -> None:
        for suffix in ("/report.md", "/result.json"):
            with self.subTest(suffix=suffix):
                status, content_type, _body = http_text(
                    self.base + "/api/runs/does-not-exist" + suffix
                )
                self.assertEqual(status, 404)
                self.assertIn("application/json", content_type)


if __name__ == "__main__":
    unittest.main()
