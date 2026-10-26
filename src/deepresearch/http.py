"""Tiny HTTP client built on :mod:`urllib` — no third-party dependency.

Every network call in DeepResearch goes through :class:`HttpClient` so that
retries, timeouts, user-agent strings, size limits and decoding behave
identically for the LLM, the search backends and the page fetcher.
"""

from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional

from .errors import FetchError

__all__ = ["DEFAULT_USER_AGENT", "HttpClient", "HttpError", "HttpResponse"]

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; DeepResearch/0.1; +https://github.com/qiebai233/ai-deep-research-assistant)"
)

_RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


class HttpError(FetchError):
    """A request failed after all retries (or with a non-retryable status)."""

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        url: str = "",
        body: str = "",
    ) -> None:
        super().__init__(message)
        self.status = status
        self.url = url
        self.body = body


@dataclass
class HttpResponse:
    url: str
    status: int
    text: str
    headers: Dict[str, str] = field(default_factory=dict)
    content_type: str = ""

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def json(self) -> Any:
        try:
            return json.loads(self.text)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise HttpError(f"invalid JSON from {self.url}: {exc}", url=self.url) from exc


class HttpClient:
    """Small, polite HTTP client with retries, gzip support and a byte cap."""

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: float = 30.0,
        max_retries: int = 2,
        backoff: float = 0.7,
        max_bytes: int = 4_000_000,
        sleeper=time.sleep,
    ) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.backoff = max(0.0, float(backoff))
        self.max_bytes = max_bytes
        self._sleep = sleeper

    # -- public API --------------------------------------------------------- #
    def get(
        self,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        timeout: Optional[float] = None,
        max_bytes: Optional[int] = None,
    ) -> HttpResponse:
        return self.request("GET", url, headers=headers, timeout=timeout, max_bytes=max_bytes)

    def post_json(
        self,
        url: str,
        payload: Mapping[str, Any],
        *,
        headers: Optional[Mapping[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> HttpResponse:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        merged = {"Content-Type": "application/json", "Accept": "application/json"}
        merged.update(dict(headers or {}))
        return self.request("POST", url, body=body, headers=merged, timeout=timeout)

    def request(
        self,
        method: str,
        url: str,
        *,
        body: Optional[bytes] = None,
        headers: Optional[Mapping[str, str]] = None,
        timeout: Optional[float] = None,
        max_bytes: Optional[int] = None,
    ) -> HttpResponse:
        if not url.lower().startswith(("http://", "https://")):
            raise HttpError(f"unsupported URL scheme: {url!r}", url=url)
        timeout = self.timeout if timeout is None else timeout
        max_bytes = self.max_bytes if max_bytes is None else max_bytes
        last_error: Optional[HttpError] = None

        for attempt in range(self.max_retries + 1):
            if attempt:
                self._sleep(self.backoff * (2 ** (attempt - 1)))
            try:
                return self._once(method, url, body, headers, timeout, max_bytes)
            except HttpError as exc:
                last_error = exc
                retryable = exc.status is None or exc.status in _RETRY_STATUS
                if not retryable or attempt >= self.max_retries:
                    raise
        raise last_error or HttpError("request failed", url=url)  # pragma: no cover

    # -- internals ---------------------------------------------------------- #
    def _once(
        self,
        method: str,
        url: str,
        body: Optional[bytes],
        headers: Optional[Mapping[str, str]],
        timeout: float,
        max_bytes: int,
    ) -> HttpResponse:
        merged = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        }
        merged.update({k: v for k, v in dict(headers or {}).items() if v is not None})
        request = urllib.request.Request(url, data=body, headers=merged, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = int(getattr(response, "status", 200))
                raw = response.read(max_bytes + 1)
                resp_headers = {k.lower(): v for k, v in response.headers.items()}
                if len(raw) > max_bytes:
                    raw = raw[:max_bytes]
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read(2000).decode("utf-8", "replace")
            except Exception:  # pragma: no cover - body already consumed
                pass
            raise HttpError(
                f"HTTP {exc.code} for {url}",
                status=exc.code,
                url=url,
                body=detail,
            ) from exc
        except urllib.error.URLError as exc:
            raise HttpError(f"network error for {url}: {exc.reason}", url=url) from exc
        except TimeoutError as exc:
            raise HttpError(f"timed out after {timeout:.0f}s: {url}", url=url) from exc
        except OSError as exc:
            raise HttpError(f"socket error for {url}: {exc}", url=url) from exc

        encoding = resp_headers.get("content-encoding", "").lower()
        if encoding == "gzip" or (not encoding and raw[:2] == b"\x1f\x8b"):
            try:
                raw = gzip.decompress(raw)
            except OSError:  # pragma: no cover - truncated stream
                pass
        elif encoding == "deflate":
            try:
                raw = zlib.decompress(raw)
            except zlib.error:  # pragma: no cover - raw deflate
                raw = zlib.decompress(raw, -zlib.MAX_WBITS)

        content_type = resp_headers.get("content-type", "")
        charset = _charset_from_headers(content_type)
        text = raw.decode(charset, errors="replace")
        return HttpResponse(
            url=url,
            status=status,
            text=text,
            headers=resp_headers,
            content_type=content_type,
        )


def _charset_from_headers(content_type: str) -> str:
    for part in content_type.split(";")[1:]:
        key, _, value = part.strip().partition("=")
        if key.lower().strip() == "charset" and value:
            candidate = value.strip().strip("'\"")
            try:
                "".encode(candidate)
                return candidate
            except LookupError:
                break
    return "utf-8"


def quote_url(url: str) -> str:
    """Percent-encode non-ASCII characters while leaving the URL structure intact."""
    parts = urllib.parse.urlsplit(url.strip())
    path = urllib.parse.quote(parts.path, safe="/%:@!$&'()*+,;=-._~")
    query = urllib.parse.quote(parts.query, safe="=&%:@!$'()*+,;/?-._~")
    fragment = urllib.parse.quote(parts.fragment, safe="=&?/:@!$'()*+,;-._~")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, fragment))
