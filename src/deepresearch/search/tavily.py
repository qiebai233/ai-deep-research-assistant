"""Tavily search backend (``POST https://api.tavily.com/search``)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..config import Settings
from ..errors import ConfigError, SearchError
from ..http import DEFAULT_USER_AGENT, HttpClient, HttpError
from ..models import SearchHit

__all__ = ["DEFAULT_ENDPOINT", "TavilySearch"]

DEFAULT_ENDPOINT = "https://api.tavily.com/search"


class TavilySearch:
    """Search provider for the Tavily API."""

    name = "tavily"

    def __init__(
        self,
        settings: Settings,
        http: Optional[HttpClient] = None,
        *,
        endpoint: Optional[str] = None,
    ) -> None:
        self.settings = settings
        self.api_key = (settings.tavily_api_key or "").strip()
        if not self.api_key:
            raise ConfigError(
                "search provider 'tavily' needs TAVILY_API_KEY (get one at https://tavily.com)"
            )
        self.endpoint = endpoint or DEFAULT_ENDPOINT
        self.search_depth = (settings.tavily_search_depth or "basic").strip().lower()
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
        """Run one Tavily query and map ``results[]`` to :class:`SearchHit`."""
        query_text = " ".join(str(query or "").split())
        if not query_text:
            return []
        limit = max(1, min(int(max_results or 6), 20))
        payload: Dict[str, Any] = {
            "api_key": self.api_key,
            "query": query_text,
            "max_results": limit,
            "search_depth": self.search_depth,
            "include_answer": False,
        }
        days = recency_days if recency_days is not None else self.settings.search_recency_days
        if days and int(days) > 0:
            payload["days"] = int(days)
        try:
            response = self.http.post_json(self.endpoint, payload)
        except HttpError as exc:
            raise SearchError(f"tavily search failed for {query_text!r}: {exc}") from exc
        try:
            data = response.json()
        except HttpError as exc:
            raise SearchError(f"tavily returned invalid JSON for {query_text!r}: {exc}") from exc
        if not isinstance(data, dict):
            raise SearchError(f"tavily returned an unexpected payload: {type(data).__name__}")
        raw_results = data.get("results")
        if not isinstance(raw_results, list):
            return []
        hits: List[SearchHit] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            url = _text(item.get("url"))
            if not url:
                continue
            hits.append(
                SearchHit(
                    url=url,
                    title=_text(item.get("title")) or url,
                    snippet=_text(item.get("content") or item.get("snippet")),
                    score=_score(item.get("score")),
                    provider="tavily",
                    published=_optional_text(
                        item.get("published_date") or item.get("publishedDate")
                    ),
                )
            )
            if len(hits) >= limit:
                break
        return hits

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"TavilySearch(endpoint={self.endpoint!r})"


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
