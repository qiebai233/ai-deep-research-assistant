"""Web-search provider interface."""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from ..models import SearchHit

__all__ = ["SearchProvider"]


@runtime_checkable
class SearchProvider(Protocol):
    """Protocol implemented by every search backend."""

    name: str

    def search(
        self,
        query: str,
        *,
        max_results: int = 6,
        recency_days: int | None = None,
    ) -> Sequence[SearchHit]:
        """Return ranked results for ``query`` (never raises for a single bad query
        when the provider can degrade gracefully; raises
        :class:`~deepresearch.errors.SearchError` otherwise)."""
        ...
