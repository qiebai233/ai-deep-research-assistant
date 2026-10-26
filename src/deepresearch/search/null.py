"""``none`` search backend: no web access, model knowledge only."""

from __future__ import annotations

from typing import List, Optional

from ..models import SearchHit

__all__ = ["NullSearch"]


class NullSearch:
    """A provider that always returns no results (offline knowledge mode)."""

    name = "none"

    def __init__(self, settings: object = None) -> None:
        self.settings = settings

    def search(
        self,
        query: str,
        *,
        max_results: int = 6,
        recency_days: Optional[int] = None,
    ) -> List[SearchHit]:
        """Always return ``[]`` — the agent degrades to knowledge-only mode."""
        return []

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "NullSearch()"
