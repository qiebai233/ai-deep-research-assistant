"""Fetcher factory and public fetch helpers.

``build_fetcher`` picks the offline :class:`~deepresearch.fetch.mock.MockFetcher`
when both the LLM and the search provider are ``mock`` (the fully offline demo),
and the cached :class:`~deepresearch.fetch.http_fetcher.HttpFetcher` otherwise.
"""

from __future__ import annotations

from typing import Optional

from ..config import Settings
from ..http import DEFAULT_USER_AGENT, HttpClient
from .base import Fetcher
from .cache import FileCache
from .extractor import extract_main_text
from .http_fetcher import HttpFetcher
from .mock import MockFetcher

__all__ = [
    "Fetcher",
    "FileCache",
    "HttpFetcher",
    "MockFetcher",
    "build_fetcher",
    "extract_main_text",
]


def build_fetcher(
    settings: Settings,
    *,
    http: Optional[HttpClient] = None,
    cache: Optional[FileCache] = None,
) -> Fetcher:
    """Create the document fetcher described by ``settings``.

    Fully offline settings (``llm_provider == "mock"`` *and*
    ``search_provider == "mock"``) get :class:`MockFetcher`; everything else gets
    a real :class:`HttpFetcher` with the file cache enabled as configured.
    """
    if (
        str(getattr(settings, "llm_provider", "") or "").strip().lower() == "mock"
        and str(getattr(settings, "search_provider", "") or "").strip().lower() == "mock"
    ):
        return MockFetcher(settings)
    client = http
    if client is None:
        client = HttpClient(
            user_agent=settings.user_agent or DEFAULT_USER_AGENT,
            timeout=float(settings.fetch_timeout or 20.0),
            max_retries=1,
        )
    if cache is None and settings.use_cache and settings.cache_dir:
        cache = FileCache(settings.cache_dir, settings.cache_ttl_hours)
    return HttpFetcher(settings, http=client, cache=cache)
