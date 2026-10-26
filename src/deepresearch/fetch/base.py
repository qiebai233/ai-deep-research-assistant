"""Page-fetching and main-content-extraction interface."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..models import Document

__all__ = ["Fetcher"]


@runtime_checkable
class Fetcher(Protocol):
    """Protocol implemented by every document fetcher."""

    name: str

    def fetch(self, url: str) -> Document:
        """Download ``url`` and return cleaned main text.

        Implementations must not raise for ordinary failures (404, timeouts,
        PDFs, empty pages): return a :class:`~deepresearch.models.Document` with
        ``status="failed"`` and an ``error`` instead, so one broken link never
        kills a research run.
        """
        ...
