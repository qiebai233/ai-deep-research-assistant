"""HTTP document fetcher with caching and main-text extraction.

``HttpFetcher`` is the only place DeepResearch downloads arbitrary pages.  It is
deliberately defensive: 404s, timeouts, PDFs, empty pages and malformed HTML all
come back as ``Document(status="failed")`` so one broken link can never kill a
research run.
"""

from __future__ import annotations

import urllib.parse
from typing import Optional

from ..config import Settings
from ..http import DEFAULT_USER_AGENT, HttpClient, HttpError
from ..models import Document
from .cache import FileCache
from .extractor import extract_main_text

__all__ = ["HttpFetcher"]

#: Content types that a text extractor can work with; an empty header is tried.
_SUPPORTED_HINTS = ("html", "text/plain")


class HttpFetcher:
    """Download pages over HTTP(S) and return cleaned main text."""

    name = "http"

    def __init__(
        self,
        settings: Settings,
        http: Optional[HttpClient] = None,
        cache: Optional[FileCache] = None,
    ) -> None:
        self.settings = settings
        self.timeout = float(settings.fetch_timeout or 20.0)
        self.max_chars = max(0, int(settings.fetch_max_chars or 0))
        self.http = (
            http
            if http is not None
            else HttpClient(
                user_agent=settings.user_agent or DEFAULT_USER_AGENT,
                timeout=self.timeout,
                max_retries=1,
            )
        )
        if cache is None and settings.use_cache and settings.cache_dir:
            cache = FileCache(settings.cache_dir, settings.cache_ttl_hours)
        self.cache = cache

    def fetch(self, url: str) -> Document:
        """Fetch ``url``; ordinary failures are returned, never raised."""
        target = str(url or "").strip()
        try:
            if not target:
                return Document(url="", status="failed", error="empty URL")
            if self.cache is not None:
                cached = self.cache.get(target)
                if cached is not None:
                    return cached
            response = self.http.get(target, timeout=self.timeout)
            content_type = (
                response.content_type or response.headers.get("content-type") or ""
            ).strip()
            if not _is_supported(content_type):
                return Document(
                    url=target,
                    status="failed",
                    error=f"unsupported content type: {content_type or 'unknown'}",
                    http_status=response.status,
                    content_type=content_type,
                )
            title, text = extract_main_text(response.text, target)
            text = _truncate(text, self.max_chars)
            if not text.strip():
                return Document(
                    url=target,
                    status="failed",
                    error="no extractable text",
                    http_status=response.status,
                    content_type=content_type,
                )
            document = Document(
                url=target,
                title=title or _title_from_url(target),
                text=text,
                status="ok",
                http_status=response.status,
                content_type=content_type,
            )
            if self.cache is not None:
                self.cache.put(target, document)
            return document
        except HttpError as exc:
            return Document(
                url=target,
                status="failed",
                error=_short_error(exc),
                http_status=exc.status,
            )
        except Exception as exc:  # noqa: BLE001 - a fetcher must never break a run
            return Document(
                url=target,
                status="failed",
                error=_short_error(exc),
            )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"HttpFetcher(timeout={self.timeout!r}, max_chars={self.max_chars!r})"


def _is_supported(content_type: str) -> bool:
    lowered = str(content_type or "").strip().lower()
    if not lowered:
        return True
    return any(hint in lowered for hint in _SUPPORTED_HINTS)


def _truncate(text: str, max_chars: int) -> str:
    if max_chars > 0 and len(text) > max_chars:
        if max_chars <= 1:
            return "…"
        return text[: max_chars - 1].rstrip() + "…"
    return text


def _short_error(exc: BaseException, limit: int = 300) -> str:
    message = " ".join(str(exc or "").split())
    if len(message) > limit:
        message = message[: limit - 1].rstrip() + "…"
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def _title_from_url(url: str) -> str:
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:  # pragma: no cover - malformed URL
        return url
    host = parts.netloc.rsplit("@", 1)[-1].split(":", 1)[0]
    return host[4:] if host.startswith("www.") else host or url
