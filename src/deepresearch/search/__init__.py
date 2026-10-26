"""Search provider factory.

``build_search`` maps ``Settings.search_provider`` to a concrete backend:

* ``tavily`` — Tavily API (needs ``TAVILY_API_KEY``).
* ``searxng`` — self-hosted SearXNG (needs ``SEARXNG_URL``).
* ``none`` — no web access (model knowledge only).
* ``mock`` — deterministic synthetic results for the offline demo/CI.

Missing credentials or an unknown provider raise
:class:`~deepresearch.errors.ConfigError` at construction time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ..config import Settings
from ..errors import ConfigError
from .base import SearchProvider
from .mock import MockSearch
from .null import NullSearch
from .searxng import SearxngSearch
from .tavily import TavilySearch

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..http import HttpClient

__all__ = [
    "MockSearch",
    "NullSearch",
    "SearchProvider",
    "SearxngSearch",
    "TavilySearch",
    "build_search",
]


def build_search(
    settings: Settings,
    *,
    http: Optional["HttpClient"] = None,
) -> SearchProvider:
    """Create the web-search provider described by ``settings``."""
    provider = str(getattr(settings, "search_provider", "") or "none").strip().lower()
    if provider in ("", "none"):
        return NullSearch(settings)
    if provider == "mock":
        return MockSearch(settings)
    if provider == "tavily":
        if not str(getattr(settings, "tavily_api_key", "") or "").strip():
            raise ConfigError(
                "search provider 'tavily' needs TAVILY_API_KEY "
                "(get one at https://tavily.com), or use --search none"
            )
        return TavilySearch(settings, http=http)
    if provider == "searxng":
        if not str(getattr(settings, "searxng_url", "") or "").strip():
            raise ConfigError("search provider 'searxng' needs SEARXNG_URL")
        return SearxngSearch(settings, http=http)
    raise ConfigError(
        f"unknown search provider {provider!r}; choose from: tavily, searxng, none, mock"
    )
