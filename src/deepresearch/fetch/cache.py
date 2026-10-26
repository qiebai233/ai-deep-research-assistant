"""Tiny JSON-file cache for fetched documents.

One file per URL (``sha1(url).json``) so concurrent runs and repeated fetches of
the same page are cheap.  The cache is deliberately silent: corrupt entries,
permission errors or a disabled cache all degrade to a cache miss, never to a
crash — a broken cache must not break a research run.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import fields
from pathlib import Path
from typing import Any, Dict, Optional

from ..models import Document, to_jsonable

__all__ = ["FileCache"]

_DOCUMENT_FIELDS = frozenset(field.name for field in fields(Document))


class FileCache:
    """URL → :class:`~deepresearch.models.Document` cache backed by JSON files."""

    def __init__(self, cache_dir: Optional[str], ttl_hours: float = 24.0) -> None:
        directory = str(cache_dir or "").strip()
        self.cache_dir: Optional[Path] = Path(directory) if directory else None
        try:
            self.ttl_hours = float(ttl_hours)
        except (TypeError, ValueError):
            self.ttl_hours = 0.0
        self.enabled = self.cache_dir is not None and self.ttl_hours > 0

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def get(self, url: str) -> Optional[Document]:
        """Return a cached fresh document for ``url``, or ``None`` on a miss."""
        if not self.enabled or not url:
            return None
        path = self._path(url)
        try:
            if not path.is_file():
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        cached_at = _as_float(payload.get("cached_at"))
        if cached_at is None:
            try:
                cached_at = path.stat().st_mtime
            except OSError:
                return None
        if time.time() - cached_at > self.ttl_hours * 3600.0:
            return None
        data = payload.get("document")
        if not isinstance(data, dict):
            return None
        kwargs: Dict[str, Any] = {
            key: value for key, value in data.items() if key in _DOCUMENT_FIELDS
        }
        if not str(kwargs.get("url") or "").strip():
            kwargs["url"] = url
        try:
            return Document(**kwargs)
        except TypeError:  # pragma: no cover - future schema drift
            return None

    def put(self, url: str, document: Document) -> None:
        """Persist ``document`` for ``url`` (atomic write; failures are ignored)."""
        if not self.enabled or not url or not isinstance(document, Document):
            return
        path = self._path(url)
        payload = {
            "url": url,
            "cached_at": time.time(),
            "document": to_jsonable(document),
        }
        temp = path.with_name(
            f"{path.name}.{os.getpid()}.{threading.get_ident()}.{time.time_ns()}.tmp"
        )
        try:
            assert self.cache_dir is not None
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(temp, path)
        except OSError:
            try:
                temp.unlink()
            except OSError:
                pass

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"FileCache(cache_dir={str(self.cache_dir)!r}, ttl_hours={self.ttl_hours!r})"

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _path(self, url: str) -> Path:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
        assert self.cache_dir is not None
        return self.cache_dir / f"{digest}.json"


def _as_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number
