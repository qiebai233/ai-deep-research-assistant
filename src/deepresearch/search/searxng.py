"""SearXNG search backend (self-hosted, JSON API)."""

from __future__ import annotations

import urllib.parse
from typing import Any, List, Optional

from ..config import Settings
from ..errors import ConfigError, SearchError
from ..http import DEFAULT_USER_AGENT, HttpClient, HttpError
from ..models import SearchHit

__all__ = ["SearxngSearch"]


class SearxngSearch:
    """Search provider for a self-hosted SearXNG instance."""

    name = "searxng"

    def __init__(self, settings: Settings, http: Optional[HttpClient] = None) -> None:
        self.settings = settings
        base = (settings.searxng_url or "").strip().rstrip("/")
        if not base:
            raise ConfigError("search provider 'searxng' needs SEARXNG_URL")
        if not base.startswith(("http://", "https://")):
            raise ConfigError(f"searxng_url must start with http(s)://, got {base!r}")
        self.base_url = base
        self.http = http or HttpClient(
            user_agent=settings.user_agent or DEFAULT_USER_AGENT,
            timeout=float(settings.search_timeout or 20.0),
            max_retries=max(0, int(settings.search_max_retries or 0)),
        )

    def search(
        self,
        query: str,
        *,
        max_results: int = 6,
        recency_days: Optional[int] = None,
    ) -> List[SearchHit]:
        """Run one SearXNG query and map ``results[]`` to :class:`SearchHit`."""
        query_text = " ".join(str(query or "").split())
        if not query_text:
            return []
        limit = max(1, min(int(max_results or 6), 20))
        english = str(self.settings.language or "zh").lower().startswith("en")
        params = {
            "q": query_text,
            "format": "json",
            "language": "en-US" if english else "zh-CN",
        }
        days = recency_days if recency_days is not None else self.settings.search_recency_days
        if days and int(days) > 0:
            params["time_range"] = _time_range(int(days))
        url = f"{self.base_url}/search?{urllib.parse.urlencode(params)}"
        try:
            response = self.http.get(url, headers={"Accept": "application/json"})
        except HttpError as exc:
            raise SearchError(f"searxng search failed for {query_text!r}: {exc}") from exc
        try:
            data = response.json()
        except HttpError as exc:
            raise SearchError(f"searxng returned invalid JSON for {query_text!r}: {exc}") from exc
        if not isinstance(data, dict):
            raise SearchError(f"searxng returned an unexpected payload: {type(data).__name__}")
        raw_results = data.get("results")
        if not isinstance(raw_results, list):
            return []
        hits: List[SearchHit] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            url_value = _text(item.get("url"))
            if not url_value:
                continue
            hits.append(
                SearchHit(
                    url=url_value,
                    title=_text(item.get("title")) or url_value,
                    snippet=_text(item.get("content") or item.get("snippet")),
                    score=_score(item.get("score")),
                    provider="searxng",
                    published=_optional_text(
                        item.get("publishedDate") or item.get("published_date")
                    ),
                )
            )
            if len(hits) >= limit:
                break
        return hits

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"SearxngSearch(base_url={self.base_url!r})"


def _text(value: Any, limit: int = 2000) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _optional_text(value: Any) -> Optional[str]:
    text = _text(value, 80)
    return text or None


def _score(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _time_range(days: int) -> str:
    if days <= 1:
        return "day"
    if days <= 7:
        return "week"
    if days <= 31:
        return "month"
    return "year"
