"""Tests for the fetch layer: extraction, cache, HTTP fetcher and mock fetcher.

All network traffic is served by ``tests.support.LocalServer`` (or a hanging raw
socket for the timeout case); the suite never touches the real internet.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import threading
import time
import unittest
from typing import Any, Dict, Tuple

from deepresearch.config import Settings
from deepresearch.fetch import (
    FileCache,
    HttpFetcher,
    MockFetcher,
    build_fetcher,
    extract_main_text,
)
from deepresearch.http import HttpClient
from deepresearch.models import Document
from tests.support import LocalServer, mock_settings, temp_workspace

ARTICLE_HTML = """<!doctype html>
<html><head>
<title>固态电池进展 | 示例站</title>
<meta name="description" content="DESCRIPTION_MARKER">
</head>
<body>
<header><nav class="menu"><a href="/">首页</a> HEADER_NAV_MARKER</nav></header>
<script>window.ANALYTICS = "SCRIPT_MARKER";</script>
<style>.ad { display: none } /* STYLE_MARKER */</style>
<main>
<article>
<h1>固态电池产业化进展</h1>
<p>2025 年以来，固态电池的产业化节奏明显加快，头部厂商公布了多条中试线计划，样本覆盖超过 120 家企业与 40 个城市。</p>
<p>2025 年以来，固态电池的产业化节奏明显加快，头部厂商公布了多条中试线计划，样本覆盖超过 120 家企业与 40 个城市。</p>
<p>从关键指标看，能量密度提升约 18.4%，成本下降 12.5%，但量产良率仍低于 70%，数据由 AT&amp;T 与多家机构联合发布。</p>
<p>风险方面，硫化物路线的材料成本与设备投资仍然偏高，监管标准尚未统一，行业需要更多一手数据来验证规模化能力。</p>
<p>综合来看，未来 2–3 年将是固态电池从实验室走向量产的关键窗口，建议持续跟踪政策口径与头部企业的产能爬坡情况。</p>
<p>以上判断基于公开资料整理，引用时应保留原始统计口径，并结合最新的一手数据交叉验证，避免单一来源偏差。</p>
</article>
</main>
<aside>ASIDE_AD_MARKER 广告位</aside>
<footer>FOOTER_MARKER 版权所有</footer>
</body></html>"""

LONG_PLAIN_TEXT = " ".join(
    ["这是没有段落标签的纯文本正文，用于验证抽取器的整页回退逻辑是否正常工作。"] * 8
)


def _http(**overrides: Any) -> HttpClient:
    options: Dict[str, Any] = {"timeout": 5.0, "backoff": 0.0, "sleeper": lambda _s: None}
    options.update(overrides)
    return HttpClient(**options)


def _html_route(html: str, status: int = 200) -> Any:
    def route(_method: str, _headers: Dict[str, str], _body: bytes) -> Tuple[int, Any, bytes]:
        return status, {"Content-Type": "text/html; charset=utf-8"}, html.encode("utf-8")

    return route


class ExtractMainTextTests(unittest.TestCase):
    def test_title_and_article_text(self) -> None:
        title, text = extract_main_text(ARTICLE_HTML, "https://example.com/a")
        self.assertEqual(title, "固态电池进展 | 示例站")
        self.assertIn("固态电池产业化进展", text)
        self.assertIn("能量密度提升约 18.4%", text)
        self.assertIn("AT&T", text)
        self.assertGreaterEqual(len(text), 200)

    def test_boilerplate_is_removed(self) -> None:
        _title, text = extract_main_text(ARTICLE_HTML, "https://example.com/a")
        for marker in (
            "HEADER_NAV_MARKER",
            "SCRIPT_MARKER",
            "STYLE_MARKER",
            "ASIDE_AD_MARKER",
            "FOOTER_MARKER",
            "DESCRIPTION_MARKER",
        ):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, text)

    def test_entity_unescaped_and_duplicates_removed(self) -> None:
        _title, text = extract_main_text(ARTICLE_HTML, "https://example.com/a")
        self.assertIn("AT&T", text)
        self.assertNotIn("&amp;", text)
        self.assertEqual(text.count("2025 年以来，固态电池的产业化节奏明显加快"), 1)

    def test_og_title_preferred(self) -> None:
        html = (
            "<html><head><title>Tag Title</title>"
            '<meta property="og:title" content="OG Title"></head>'
            "<body><p>" + "长正文内容。" * 60 + "</p></body></html>"
        )
        title, _text = extract_main_text(html, "https://example.com/x")
        self.assertEqual(title, "OG Title")

    def test_title_falls_back_to_h1_then_url(self) -> None:
        html = "<html><body><h1>只有一个H1标题</h1><p>" + "正文内容。" * 80 + "</p></body></html>"
        title, _text = extract_main_text(html)
        self.assertEqual(title, "只有一个H1标题")
        title_from_url, _text = extract_main_text(
            "<html><body><p>" + "正文。" * 120 + "</p></body></html>", "https://www.example.com/a/b"
        )
        self.assertEqual(title_from_url, "example.com")

    def test_short_article_falls_back_to_whole_body(self) -> None:
        html = (
            "<html><body>"
            "<article><p>ARTICLE_SHORT_MARKER 太短。</p></article>"
            "<div><p>BODY_LONG_MARKER "
            + "整页正文需要回退抽取，确保内容足够长。"
            * 20
            + "</p></div>"
            "</body></html>"
        )
        _title, text = extract_main_text(html)
        self.assertIn("BODY_LONG_MARKER", text)

    def test_plain_text_page(self) -> None:
        html = "<html><body>" + LONG_PLAIN_TEXT + "</body></html>"
        _title, text = extract_main_text(html)
        self.assertIn("纯文本正文", text)
        self.assertGreaterEqual(len(text), 200)

    def test_malformed_html_does_not_raise(self) -> None:
        title, text = extract_main_text("<p>未闭合标签 <div><script>oops")
        self.assertIsInstance(title, str)
        self.assertIsInstance(text, str)


class FileCacheTests(unittest.TestCase):
    def test_put_and_get_roundtrip(self) -> None:
        with temp_workspace() as tmp:
            cache = FileCache(os.path.join(tmp, "cache"), ttl_hours=24.0)
            url = "https://example.com/article"
            document = Document(
                url=url,
                title="缓存标题",
                text="缓存正文内容",
                status="ok",
                http_status=200,
                content_type="text/html",
            )
            cache.put(url, document)
            cached = cache.get(url)
            self.assertIsNotNone(cached)
            assert cached is not None
            self.assertEqual(cached.url, url)
            self.assertEqual(cached.title, "缓存标题")
            self.assertEqual(cached.text, "缓存正文内容")
            self.assertEqual(cached.status, "ok")
            self.assertEqual(cached.http_status, 200)
            filename = hashlib.sha1(url.encode("utf-8")).hexdigest() + ".json"
            self.assertTrue(os.path.isfile(os.path.join(tmp, "cache", filename)))

    def test_miss_returns_none(self) -> None:
        with temp_workspace() as tmp:
            cache = FileCache(os.path.join(tmp, "cache"))
            self.assertIsNone(cache.get("https://example.com/missing"))

    def test_corrupt_entry_is_a_miss(self) -> None:
        with temp_workspace() as tmp:
            cache = FileCache(os.path.join(tmp, "cache"))
            url = "https://example.com/corrupt"
            cache.put(url, Document(url=url, title="t", text="x"))
            path = cache._path(url)
            path.write_text("this is not json", encoding="utf-8")
            self.assertIsNone(cache.get(url))

    def test_ttl_expiry(self) -> None:
        with temp_workspace() as tmp:
            cache = FileCache(os.path.join(tmp, "cache"), ttl_hours=1.0)
            url = "https://example.com/old"
            cache.put(url, Document(url=url, title="old", text="old text"))
            path = cache._path(url)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["cached_at"] = time.time() - 2 * 3600.0
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertIsNone(cache.get(url))

    def test_ttl_zero_disables_cache(self) -> None:
        with temp_workspace() as tmp:
            cache = FileCache(os.path.join(tmp, "cache"), ttl_hours=0.0)
            self.assertFalse(cache.enabled)
            url = "https://example.com/disabled"
            cache.put(url, Document(url=url, title="t", text="x"))
            self.assertFalse(os.path.isdir(os.path.join(tmp, "cache")))
            self.assertIsNone(cache.get(url))


class HttpFetcherTests(unittest.TestCase):
    def _settings(self, **overrides: Any) -> Settings:
        values: Dict[str, Any] = {
            "llm_provider": "openai",
            "llm_api_key": "k",
            "search_provider": "tavily",
            "tavily_api_key": "t",
            "fetch_timeout": 5.0,
            "cache_dir": "",
            "use_cache": False,
        }
        values.update(overrides)
        return Settings(**values)

    def test_successful_fetch(self) -> None:
        with LocalServer({"/good": _html_route(ARTICLE_HTML)}) as server:
            fetcher = HttpFetcher(self._settings(), http=_http())
            document = fetcher.fetch(server.url("/good"))
        self.assertEqual(document.status, "ok")
        self.assertEqual(document.http_status, 200)
        self.assertIn("html", document.content_type or "")
        self.assertIn("固态电池", document.title)
        self.assertIn("能量密度提升约 18.4%", document.text)
        self.assertGreaterEqual(len(document.text), 200)

    def test_missing_content_type_still_fetched(self) -> None:
        def route(_m: str, _h: Dict[str, str], _b: bytes) -> Tuple[int, Any, bytes]:
            return 200, {}, ARTICLE_HTML.encode("utf-8")

        with LocalServer({"/no-ctype": route}) as server:
            document = HttpFetcher(self._settings(), http=_http()).fetch(server.url("/no-ctype"))
        self.assertEqual(document.status, "ok")

    def test_404_returns_failed_document(self) -> None:
        def route(_m, _h, _b):
            return (404, {"Content-Type": "text/plain"}, b"not found")
        with LocalServer({"/missing": route}) as server:
            document = HttpFetcher(self._settings(), http=_http(max_retries=0)).fetch(
                server.url("/missing")
            )
        self.assertEqual(document.status, "failed")
        self.assertEqual(document.http_status, 404)
        self.assertIn("404", document.error or "")

    def test_non_html_content_type_is_rejected(self) -> None:
        def route(_m, _h, _b):
            return (200, {"Content-Type": "application/pdf"}, b"%PDF-1.7")
        with LocalServer({"/file.pdf": route}) as server:
            document = HttpFetcher(self._settings(), http=_http()).fetch(server.url("/file.pdf"))
        self.assertEqual(document.status, "failed")
        self.assertIn("unsupported content type", document.error or "")
        self.assertIn("application/pdf", document.error or "")

    def test_empty_page_returns_failed_document(self) -> None:
        route = _html_route("<html><body></body></html>")
        with LocalServer({"/empty": route}) as server:
            document = HttpFetcher(self._settings(), http=_http()).fetch(server.url("/empty"))
        self.assertEqual(document.status, "failed")
        self.assertIn("no extractable text", document.error or "")

    def test_text_is_truncated_to_max_chars(self) -> None:
        with LocalServer({"/long": _html_route(ARTICLE_HTML)}) as server:
            fetcher = HttpFetcher(self._settings(fetch_max_chars=300), http=_http())
            document = fetcher.fetch(server.url("/long"))
        self.assertEqual(document.status, "ok")
        self.assertLessEqual(len(document.text), 300)
        self.assertTrue(document.text.endswith("…"))

    def test_cache_avoids_second_request(self) -> None:
        calls = {"count": 0}

        def route(_m: str, _h: Dict[str, str], _b: bytes) -> Tuple[int, Any, bytes]:
            calls["count"] += 1
            return 200, {"Content-Type": "text/html; charset=utf-8"}, ARTICLE_HTML.encode()

        with temp_workspace() as tmp, LocalServer({"/cached": route}) as server:
            cache = FileCache(os.path.join(tmp, "cache"))
            fetcher = HttpFetcher(self._settings(), http=_http(), cache=cache)
            first = fetcher.fetch(server.url("/cached"))
            second = fetcher.fetch(server.url("/cached"))
        self.assertEqual(calls["count"], 1)
        self.assertEqual(first.status, "ok")
        self.assertEqual(first.text, second.text)
        self.assertEqual(first.title, second.title)

    def test_never_raises_on_bad_url(self) -> None:
        fetcher = HttpFetcher(self._settings(), http=_http())
        for url in ("", "not-a-url", "ftp://example.com/x"):
            with self.subTest(url=url):
                document = fetcher.fetch(url)
                self.assertEqual(document.status, "failed")
                self.assertTrue(document.error)

    def test_timeout_returns_failed_document(self) -> None:
        with _HangingServer() as server:
            fetcher = HttpFetcher(self._settings(), http=_http(timeout=0.2, max_retries=0))
            document = fetcher.fetch(server.url("/slow"))
        self.assertEqual(document.status, "failed")
        self.assertIn("timed", (document.error or "").lower())


class _HangingServer:
    """Raw socket server that accepts connections and never replies."""

    def __init__(self) -> None:
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind(("127.0.0.1", 0))
        self._socket.listen(5)
        self.port = int(self._socket.getsockname()[1])
        self._connections: list[socket.socket] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                connection, _address = self._socket.accept()
            except OSError:
                return
            self._connections.append(connection)

    def url(self, path: str = "/") -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def __enter__(self) -> "_HangingServer":
        self._thread.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self._stop.set()
        try:
            self._socket.close()
        except OSError:
            pass
        for connection in self._connections:
            try:
                connection.close()
            except OSError:
                pass


class MockFetcherTests(unittest.TestCase):
    def test_deterministic_document(self) -> None:
        fetcher = MockFetcher()
        url = "https://arxiv.org/abs/2409.12345"
        first = fetcher.fetch(url)
        second = fetcher.fetch(url)
        self.assertEqual(first.status, "ok")
        self.assertEqual(first.title, second.title)
        self.assertEqual(first.text, second.text)
        self.assertEqual(first.http_status, 200)
        self.assertEqual(first.url, url)

    def test_text_length_and_numbers(self) -> None:
        fetcher = MockFetcher()
        document = fetcher.fetch("https://example.com/news/ai-trends.html")
        self.assertGreaterEqual(len(document.text), 500)
        self.assertLessEqual(len(document.text), 900)
        self.assertGreaterEqual(len(re.findall(r"\d+", document.text)), 5)
        self.assertIn("example.com", document.title)
        self.assertIn("ai trends", document.title)

    def test_badlink_fails(self) -> None:
        document = MockFetcher().fetch("https://example.com/badlink-page")
        self.assertEqual(document.status, "failed")
        self.assertIn("badlink", document.error or "")

    def test_empty_url_fails(self) -> None:
        document = MockFetcher().fetch("")
        self.assertEqual(document.status, "failed")


class FetcherFactoryTests(unittest.TestCase):
    def test_mock_stack_uses_mock_fetcher(self) -> None:
        self.assertIsInstance(build_fetcher(mock_settings()), MockFetcher)

    def test_real_stack_uses_http_fetcher_with_cache(self) -> None:
        with temp_workspace() as tmp:
            settings = Settings(
                llm_provider="openai",
                llm_api_key="k",
                search_provider="tavily",
                tavily_api_key="t",
                cache_dir=os.path.join(tmp, "cache"),
            )
            fetcher = build_fetcher(settings)
        self.assertIsInstance(fetcher, HttpFetcher)
        self.assertEqual(fetcher.name, "http")
        self.assertIsNotNone(fetcher.cache)

    def test_cache_disabled_configuration(self) -> None:
        with temp_workspace() as tmp:
            settings = Settings(
                llm_provider="openai",
                llm_api_key="k",
                search_provider="tavily",
                tavily_api_key="t",
                cache_dir=os.path.join(tmp, "cache"),
                use_cache=False,
            )
            fetcher = build_fetcher(settings)
        self.assertIsInstance(fetcher, HttpFetcher)
        self.assertIsNone(fetcher.cache)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
