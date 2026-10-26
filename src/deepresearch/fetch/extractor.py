"""Boilerplate-free main-content extraction with :mod:`html.parser` only.

Real-world pages wrap the interesting text in navigation, ads, cookie banners
and footers.  This module turns arbitrary HTML into ``(title, text)``:

* ``script/style/nav/header/footer/aside/form/noscript/svg/template/...`` are
  dropped entirely;
* ``<article>``/``<main>`` blocks win over the rest of the page when they are
  long enough;
* ``h1``–``h3``, ``p`` and ``li`` become paragraphs, entities are unescaped,
  whitespace is collapsed and repeated lines are removed;
* when everything is shorter than 200 characters we fall back to the whole
  visible body text so the fetcher can still report *something*.

No third-party dependency (no bs4/trafilatura) — only the standard library.
"""

from __future__ import annotations

import re
import urllib.parse
from html.parser import HTMLParser
from typing import List, Optional, Tuple

__all__ = ["extract_main_text"]

_MIN_TEXT_CHARS = 200
_HEADING_TAGS = frozenset({"h1", "h2", "h3"})
_BLOCK_TAGS = frozenset(
    {
        "h1",
        "h2",
        "h3",
        "p",
        "li",
        "blockquote",
        "pre",
        "td",
        "th",
        "dt",
        "dd",
    }
)
_SKIP_TAGS = frozenset(
    {
        "script",
        "style",
        "nav",
        "header",
        "footer",
        "aside",
        "form",
        "noscript",
        "svg",
        "template",
        "iframe",
        "button",
        "select",
        "textarea",
        "canvas",
        "object",
    }
)
_WHITESPACE_RE = re.compile(r"\s+")


def extract_main_text(html: str, url: str = "") -> Tuple[str, str]:
    """Return ``(title, text)`` for an HTML document.

    ``url`` is only used to derive a fallback title when the page has neither
    ``<title>`` nor ``og:title``.  The function never raises: malformed markup
    is tolerated and yields whatever text could be recovered.
    """
    parser = _MainTextParser()
    try:
        parser.feed(str(html or ""))
        parser.close()
    except Exception:  # pragma: no cover - HTMLParser is extremely tolerant
        pass
    parser.finalize()
    title = parser.best_title()
    if not title:
        title = _title_from_url(url)
    return title, parser.main_text()


class _MainTextParser(HTMLParser):
    """Collect visible block text, remembering which blocks belong to <main>."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._title_parts: List[str] = []
        self._og_title = ""
        self._blocks_all: List[str] = []
        self._blocks_main: List[str] = []
        self._headings: List[str] = []
        self._raw_parts: List[str] = []
        self._skip_depth = 0
        self._main_depth = 0
        self._in_title = False
        self._capture = ""
        self._capture_in_main = False
        self._buffer: List[str] = []

    # -- HTMLParser hooks -------------------------------------------------- #
    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        name = tag.lower()
        if name == "meta":
            self._handle_meta(attrs)
            return
        if name in _SKIP_TAGS:
            if not self._skip_depth:
                self._flush()
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if name in ("article", "main"):
            self._main_depth += 1
            return
        if name == "title":
            self._in_title = True
            self._title_parts = []
            return
        if name == "br":
            if self._capture:
                self._buffer.append(" ")
            return
        if name in _BLOCK_TAGS:
            self._flush()
            self._capture = name
            self._capture_in_main = self._main_depth > 0
            self._buffer = []

    def handle_startendtag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag.lower() == "meta":
            self._handle_meta(attrs)

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name in _SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if name in ("article", "main"):
            self._main_depth = max(0, self._main_depth - 1)
            return
        if name == "title":
            self._in_title = False
            return
        if name in _BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if not data:
            return
        if self._in_title:
            self._title_parts.append(data)
            return
        if self._skip_depth:
            return
        self._raw_parts.append(data)
        if self._capture:
            self._buffer.append(data)

    # -- internals --------------------------------------------------------- #
    def _handle_meta(self, attrs: List[Tuple[str, Optional[str]]]) -> None:
        values = {str(key).lower(): str(value or "") for key, value in attrs}
        prop = (values.get("property") or values.get("name") or "").strip().lower()
        content = values.get("content", "")
        if prop in ("og:title", "twitter:title") and content and not self._og_title:
            self._og_title = content

    def _flush(self) -> None:
        if not self._capture:
            return
        text = _normalize("".join(self._buffer))
        kind = self._capture
        in_main = self._capture_in_main
        self._capture = ""
        self._buffer = []
        self._capture_in_main = False
        if not text:
            return
        self._blocks_all.append(text)
        if in_main:
            self._blocks_main.append(text)
        if kind in _HEADING_TAGS:
            self._headings.append(text)

    def finalize(self) -> None:
        """Flush a trailing open block after :meth:`close`."""
        self._flush()

    # -- results ----------------------------------------------------------- #
    def best_title(self) -> str:
        title = _normalize(self._og_title) or _normalize("".join(self._title_parts))
        return title or (self._headings[0] if self._headings else "")

    def main_text(self) -> str:
        main_lines = _dedupe(self._blocks_main)
        all_lines = _dedupe(self._blocks_all)
        main_text = "\n\n".join(main_lines)
        all_text = "\n\n".join(all_lines)
        candidate = main_text if len(main_text) >= _MIN_TEXT_CHARS else all_text
        if len(candidate) < _MIN_TEXT_CHARS:
            raw_lines = _dedupe([_normalize(part) for part in self._raw_parts])
            raw_text = "\n\n".join(raw_lines)
            if len(raw_text) > len(candidate):
                candidate = raw_text
        return candidate.strip()


# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #
def _normalize(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", str(text or "")).strip()


def _dedupe(lines: List[str]) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for line in lines:
        if len(line) < 2 or line in seen:
            continue
        seen.add(line)
        result.append(line)
    return result


def _title_from_url(url: str) -> str:
    """Derive a readable fallback title from ``url`` (host name)."""
    if not url:
        return ""
    try:
        parts = urllib.parse.urlsplit(url.strip())
    except ValueError:  # pragma: no cover - malformed URL
        return ""
    host = parts.netloc.rsplit("@", 1)[-1].split(":", 1)[0]
    return host[4:] if host.startswith("www.") else host
