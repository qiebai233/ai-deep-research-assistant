"""Tests for the search providers — fully offline, no real network.

Tavily and SearXNG are simulated with ``tests.support.LocalServer``; the mock
provider must be completely deterministic and stay inside the fixed domain pool.
"""

from __future__ import annotations

import json
import unittest
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlsplit

from deepresearch.config import Settings
from deepresearch.errors import ConfigError, SearchError
from deepresearch.http import HttpClient
from deepresearch.models import SearchHit
from deepresearch.search import (
    MockSearch,
    NullSearch,
    SearxngSearch,
    TavilySearch,
    build_search,
)
from deepresearch.search.mock import DOMAIN_POOL
from tests.support import LocalServer, mock_settings

TAVILY_PAYLOAD: Dict[str, Any] = {
    "query": "solid state battery",
    "results": [
        {
            "url": "https://example.com/a",
            "title": "Result A",
            "content": "content A",
            "score": 0.91,
            "published_date": "2024-11-05",
        },
        {
            "url": "https://example.com/b",
            "title": "Result B",
            "content": "content B",
            "score": 0.82,
        },
        {
            "url": "https://example.com/c",
        },
        {"title": "missing url", "content": "should be skipped"},
        "not-a-dict",
    ],
}

SEARXNG_PAYLOAD: Dict[str, Any] = {
    "query": "固态电池",
    "results": [
        {
            "url": "https://example.com/s1",
            "title": "SearXNG one",
            "content": "content one",
            "score": 1.2,
            "publishedDate": "2025-01-12",
        },
        {"url": "https://example.com/s2"},
        {"title": "missing url"},
    ],
}


def _http(**overrides: Any) -> HttpClient:
    options: Dict[str, Any] = {"timeout": 5.0, "backoff": 0.0, "sleeper": lambda _s: None}
    options.update(overrides)
    return HttpClient(**options)


class _RecordingHTTP:
    """Minimal HttpClient wrapper that records the full request URLs."""

    def __init__(self, inner: HttpClient) -> None:
        self.inner = inner
        self.urls: List[str] = []

    def get(self, url: str, **kwargs: Any) -> Any:
        self.urls.append(url)
        return self.inner.get(url, **kwargs)

    def post_json(self, url: str, payload: Any, **kwargs: Any) -> Any:
        self.urls.append(url)
        return self.inner.post_json(url, payload, **kwargs)


def _json_route(payload: Any):
    body = json.dumps(payload).encode("utf-8")
    return lambda _method, _headers, _body: (200, {"Content-Type": "application/json"}, body)


class TavilySearchTests(unittest.TestCase):
    def _settings(self, **overrides: Any) -> Settings:
        values: Dict[str, Any] = {
            "search_provider": "tavily",
            "tavily_api_key": "tvly-test-key",
            "tavily_search_depth": "advanced",
        }
        values.update(overrides)
        return Settings(**values)

    def test_request_payload_and_result_mapping(self) -> None:
        captured: Dict[str, Any] = {}

        def route(method: str, headers: Dict[str, str], body: bytes) -> Any:
            captured["method"] = method
            captured["body"] = json.loads(body.decode("utf-8"))
            return (
                200,
                {"Content-Type": "application/json"},
                json.dumps(TAVILY_PAYLOAD).encode("utf-8"),
            )

        with LocalServer({"/search": route}) as server:
            provider = TavilySearch(
                self._settings(search_recency_days=30),
                http=_http(),
                endpoint=server.url("/search"),
            )
            hits = provider.search("solid state battery", max_results=4)

        self.assertEqual(captured["method"], "POST")
        payload = captured["body"]
        self.assertEqual(payload["api_key"], "tvly-test-key")
        self.assertEqual(payload["query"], "solid state battery")
        self.assertEqual(payload["max_results"], 4)
        self.assertEqual(payload["search_depth"], "advanced")
        self.assertIs(payload["include_answer"], False)
        self.assertEqual(payload["days"], 30)

        self.assertEqual(len(hits), 3)
        first = hits[0]
        self.assertIsInstance(first, SearchHit)
        self.assertEqual(first.url, "https://example.com/a")
        self.assertEqual(first.title, "Result A")
        self.assertEqual(first.snippet, "content A")
        self.assertAlmostEqual(first.score, 0.91)
        self.assertEqual(first.provider, "tavily")
        self.assertEqual(first.published, "2024-11-05")
        # Missing title/score/published must degrade gracefully.
        third = hits[2]
        self.assertEqual(third.url, "https://example.com/c")
        self.assertEqual(third.title, "https://example.com/c")
        self.assertEqual(third.snippet, "")
        self.assertEqual(third.score, 0.0)
        self.assertIsNone(third.published)

    def test_tolerates_missing_results_key(self) -> None:
        with LocalServer({"/search": _json_route({"answer": "no results"})}) as server:
            provider = TavilySearch(self._settings(), http=_http(), endpoint=server.url("/search"))
            self.assertEqual(provider.search("anything"), [])

    def test_http_error_becomes_search_error(self) -> None:
        def route(_m, _h, _b):
            return (500, {"Content-Type": "application/json"}, b"{}")
        with LocalServer({"/search": route}) as server:
            provider = TavilySearch(
                self._settings(), http=_http(max_retries=0), endpoint=server.url("/search")
            )
            with self.assertRaises(SearchError):
                provider.search("boom")

    def test_invalid_json_becomes_search_error(self) -> None:
        def route(_m, _h, _b):
            return (200, {"Content-Type": "application/json"}, b"<html>")
        with LocalServer({"/search": route}) as server:
            provider = TavilySearch(
                self._settings(), http=_http(max_retries=0), endpoint=server.url("/search")
            )
            with self.assertRaises(SearchError):
                provider.search("boom")


class SearxngSearchTests(unittest.TestCase):
    def _settings(self, base_url: str, **overrides: Any) -> Settings:
        values: Dict[str, Any] = {
            "search_provider": "searxng",
            "searxng_url": base_url,
            "language": "zh",
        }
        values.update(overrides)
        return Settings(**values)

    def test_request_url_and_result_mapping(self) -> None:
        with LocalServer({"/search": _json_route(SEARXNG_PAYLOAD)}) as server:
            recording = _RecordingHTTP(_http())
            provider = SearxngSearch(self._settings(server.base_url), http=recording)
            hits = provider.search("固态电池", max_results=5, recency_days=7)

        self.assertEqual(len(recording.urls), 1)
        parts = urlsplit(recording.urls[0])
        self.assertEqual(parts.path, "/search")
        query = parse_qs(parts.query)
        self.assertEqual(query["q"], ["固态电池"])
        self.assertEqual(query["format"], ["json"])
        self.assertEqual(query["language"], ["zh-CN"])
        self.assertEqual(query["time_range"], ["week"])

        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0].url, "https://example.com/s1")
        self.assertEqual(hits[0].title, "SearXNG one")
        self.assertEqual(hits[0].snippet, "content one")
        self.assertEqual(hits[0].provider, "searxng")
        self.assertEqual(hits[0].published, "2025-01-12")
        # Missing optional fields are tolerated.
        self.assertEqual(hits[1].url, "https://example.com/s2")
        self.assertEqual(hits[1].title, "https://example.com/s2")
        self.assertIsNone(hits[1].published)

    def test_english_language_parameter(self) -> None:
        with LocalServer({"/search": _json_route({"results": []})}) as server:
            recording = _RecordingHTTP(_http())
            provider = SearxngSearch(self._settings(server.base_url, language="en"), http=recording)
            self.assertEqual(provider.search("battery"), [])
        query = parse_qs(urlsplit(recording.urls[0]).query)
        self.assertEqual(query["language"], ["en-US"])

    def test_http_error_becomes_search_error(self) -> None:
        def route(_m, _h, _b):
            return (503, {"Content-Type": "text/plain"}, b"down")
        with LocalServer({"/search": route}) as server:
            provider = SearxngSearch(self._settings(server.base_url), http=_http(max_retries=0))
            with self.assertRaises(SearchError):
                provider.search("boom")


class NullAndMockSearchTests(unittest.TestCase):
    def test_null_search_is_empty(self) -> None:
        provider = NullSearch()
        self.assertEqual(provider.name, "none")
        self.assertEqual(provider.search("anything"), [])
        self.assertEqual(provider.search("anything", max_results=3), [])

    def test_mock_search_is_deterministic(self) -> None:
        provider = MockSearch()
        first = provider.search("固态电池 2025 年产业化进展")
        second = provider.search("固态电池 2025 年产业化进展")
        self.assertEqual(first, second)
        self.assertTrue(5 <= len(first) <= 6)
        self.assertEqual(provider.name, "mock")
        query = "固态电池 2025 年产业化进展"
        for hit in first:
            self.assertEqual(hit.provider, "mock")
            self.assertIn(query, hit.title)
            self.assertIn(query, hit.snippet)
            self.assertTrue(hit.url.startswith("https://"))
            self.assertIn(urlsplit(hit.url).hostname, DOMAIN_POOL)
            self.assertIsNotNone(hit.published)
            self.assertGreater(hit.score, 0.0)

    def test_mock_search_respects_max_results(self) -> None:
        provider = MockSearch()
        self.assertEqual(len(provider.search("battery", max_results=3)), 3)
        self.assertEqual(len(provider.search("battery", max_results=20)), 6)
        self.assertEqual(provider.search(""), [])

    def test_mock_search_varies_per_query(self) -> None:
        provider = MockSearch()
        first = {hit.url for hit in provider.search("solid state battery")}
        second = {hit.url for hit in provider.search("quantum computing")}
        self.assertFalse(first & second)

    def test_mock_search_english_language(self) -> None:
        settings = Settings(language="en")
        provider = MockSearch(settings)
        hits = provider.search("solid state battery")
        self.assertIn("solid state battery", hits[0].title)
        self.assertIn("research review", " ".join(hit.title for hit in hits))


class SearchFactoryTests(unittest.TestCase):
    def test_factory_mapping(self) -> None:
        self.assertIsInstance(build_search(mock_settings()), MockSearch)
        none_settings = Settings(search_provider="none")
        self.assertIsInstance(build_search(none_settings), NullSearch)
        tavily = Settings(search_provider="tavily", tavily_api_key="tvly-key")
        self.assertIsInstance(build_search(tavily), TavilySearch)
        searxng = Settings(search_provider="searxng", searxng_url="https://searx.example.com")
        self.assertIsInstance(build_search(searxng), SearxngSearch)

    def test_factory_config_errors(self) -> None:
        with self.assertRaises(ConfigError):
            build_search(Settings(search_provider="tavily"))
        with self.assertRaises(ConfigError):
            build_search(Settings(search_provider="searxng"))
        with self.assertRaises(ConfigError):
            build_search(Settings(search_provider="brave"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
