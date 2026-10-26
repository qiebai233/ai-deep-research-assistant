"""Shared, network-free test utilities (standard library only).

Every test module may import from here; only the Lead edits this file.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

from deepresearch.config import Settings
from deepresearch.events import EventSink
from deepresearch.llm.base import LLMResponse, Message

# --------------------------------------------------------------------------- #
# Local HTTP server: never touch the real internet in tests
# --------------------------------------------------------------------------- #
RouteResult = Tuple[int, Dict[str, str], bytes]
Route = Any  # RouteResult | Callable[[str, Dict[str, str], bytes], RouteResult]


class _RouteHandler(BaseHTTPRequestHandler):
    server_version = "DeepResearchTestServer/1.0"

    def _dispatch(self) -> None:
        routes: Mapping[str, Route] = getattr(self.server, "routes", {})
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        route = routes.get(self.path.split("?")[0]) or routes.get("*")
        if route is None:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"not found")
            return
        if callable(route):
            status, headers, payload = route(self.command, dict(self.headers), body)
        else:
            status, headers, payload = route
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        try:
            self.send_response(status)
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            # Timeout tests abort the connection on purpose; never spam the log.
            pass

    do_GET = _dispatch
    do_POST = _dispatch
    do_HEAD = _dispatch

    def log_message(self, *_args: Any) -> None:  # keep test output clean
        pass


class LocalServer:
    """Tiny in-process HTTP server for provider tests.

    >>> with LocalServer({"/v1/chat/completions": (200, {}, '{"ok": 1}')}) as s:
    ...     s.url("/v1/chat/completions")
    """

    def __init__(self, routes: Mapping[str, Route]) -> None:
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _RouteHandler)
        self._httpd.daemon_threads = True
        self._httpd.routes = dict(routes)
        self._thread: Optional[threading.Thread] = None
        self.requests: List[Dict[str, Any]] = []

    @property
    def port(self) -> int:
        return int(self._httpd.server_address[1])

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def url(self, path: str = "/") -> str:
        return self.base_url + path

    def start(self) -> "LocalServer":
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._httpd.shutdown()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def __enter__(self) -> "LocalServer":
        return self.start()

    def __exit__(self, *_exc: Any) -> None:
        self.stop()


# --------------------------------------------------------------------------- #
# SSE / HTTP helpers
# --------------------------------------------------------------------------- #
def http_json(url: str, *, method: str = "GET", payload: Any = None, timeout: float = 20.0) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def http_text(url: str, *, timeout: float = 20.0) -> Tuple[int, str, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return (
                int(response.status),
                response.headers.get("Content-Type", ""),
                response.read().decode("utf-8", "replace"),
            )
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read().decode("utf-8", "replace")


def parse_sse(stream: Iterable[str]) -> List[Dict[str, str]]:
    """Parse an SSE byte/text stream into ``[{event, data, id}]`` records."""
    events: List[Dict[str, str]] = []
    current: Dict[str, str] = {}
    data_lines: List[str] = []
    for raw in stream:
        line = raw.rstrip("\r\n")
        if not line:
            if current or data_lines:
                record = dict(current)
                record["data"] = "\n".join(data_lines)
                events.append(record)
            current, data_lines = {}, []
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if field == "data":
            data_lines.append(value)
        else:
            current[field] = value
    if current or data_lines:
        record = dict(current)
        record["data"] = "\n".join(data_lines)
        events.append(record)
    return events


def post_sse_events(
    url: str, payload: Any, *, timeout: float = 60.0
) -> Tuple[int, str, List[Dict[str, str]]]:
    """POST JSON and collect the SSE records returned before the stream closes."""
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), []
    with response:
        status = int(response.status)
        content_type = response.headers.get("Content-Type", "")
        raw_lines = [line.decode("utf-8", "replace") for line in response]
    return status, content_type, parse_sse(raw_lines)


# --------------------------------------------------------------------------- #
# Environment / stdout helpers
# --------------------------------------------------------------------------- #
@contextlib.contextmanager
def patch_env(updates: Mapping[str, str], *, clear: Sequence[str] = ()) -> Iterator[None]:
    """Temporarily set environment variables (and optionally unset some)."""
    saved = {key: os.environ.get(key) for key in set(updates) | set(clear)}
    for key in clear:
        os.environ.pop(key, None)
    os.environ.update({k: str(v) for k, v in updates.items()})
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextlib.contextmanager
def captured_stdout() -> Iterator[io.StringIO]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        yield buffer


class CliResult:
    def __init__(self, exit_code: int, stdout: str, stderr: str = "") -> None:
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"CliResult(exit_code={self.exit_code}, stdout={self.stdout[:200]!r})"


def run_cli(
    argv: Sequence[str],
    *,
    env: Optional[Mapping[str, str]] = None,
    clear_env: Sequence[str] = (),
) -> CliResult:
    """Invoke ``deepresearch.cli.main(argv)`` in-process and capture its output."""
    from deepresearch.cli import main

    buffer = io.StringIO()
    errors = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(errors):
        with patch_env(env or {}, clear=clear_env):
            try:
                code = int(main(list(argv)) or 0)
            except SystemExit as exc:  # argparse/CLI style exit
                code = int(exc.code or 0)
            except BaseException as exc:  # noqa: BLE001 - surfaced through the result
                code = 1
                errors.write(f"{type(exc).__name__}: {exc}")
    return CliResult(code, buffer.getvalue(), errors.getvalue())


_TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"


def temp_dir() -> str:
    """Create a throwaway directory inside the repo.

    The DSH sandbox denies creating sub-directories under the OS temp folder on
    Windows, so test artefacts live in ``<repo>/.test-tmp`` (git-ignored).
    """
    import uuid

    _TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = _TEST_TMP_ROOT / f"dr-{uuid.uuid4().hex[:12]}"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


# --------------------------------------------------------------------------- #
# Domain helpers
# --------------------------------------------------------------------------- #
def mock_settings(base: str = "", **overrides: Any) -> Settings:
    """Fully offline settings rooted in a throwaway directory."""
    root = base or temp_dir()
    defaults: Dict[str, Any] = dict(
        llm_provider="mock",
        search_provider="mock",
        out_dir=os.path.join(root, "reports"),
        cache_dir=os.path.join(root, "cache"),
        language="zh",
        depth="quick",
        fetch_concurrency=2,
    )
    defaults.update(overrides)
    settings = Settings(**defaults)
    settings._apply_preset_defaults()
    return settings


def collect_events(**kwargs: Any) -> EventSink:
    """Event sink with full history, handy for assertions."""
    kwargs.setdefault("keep_history", True)
    return EventSink(**kwargs)


def event_types(sink: EventSink) -> List[str]:
    return [event.type for event in sink.history]


def event_messages(sink: EventSink) -> List[str]:
    return [event.message for event in sink.history]


class RecordingLLM:
    """Wrap an LLMClient, recording every prompt for prompt-contract tests."""

    name = "recording"

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.calls: List[List[Message]] = []

    def complete(self, messages: Sequence[Message], **kwargs: Any) -> LLMResponse:
        self.calls.append(list(messages))
        return self.inner.complete(messages, **kwargs)

    def prompts(self) -> List[str]:
        return ["\n".join(m.content for m in call) for call in self.calls]

    def tasks(self) -> List[str]:
        import re

        found = []
        for prompt in self.prompts():
            match = re.search(r"^TASK:\s*([a-z_]+)", prompt, re.MULTILINE)
            found.append(match.group(1) if match else "")
        return found


class BadJSONLLM:
    """Always returns prose — used to test graceful degradation."""

    name = "bad-json"

    def __init__(self, text: str = "I cannot produce JSON today.") -> None:
        self.text = text
        self.calls = 0

    def complete(self, messages: Sequence[Message], **kwargs: Any) -> LLMResponse:
        self.calls += 1
        return LLMResponse(text=self.text, model="bad-json")


class ExplodingSearch:
    name = "exploding"

    def search(self, query: str, *, max_results: int = 6, recency_days: Any = None) -> Any:
        from deepresearch.errors import SearchError

        raise SearchError(f"boom: {query}")


class SlowLLM:
    """Sleeps on every call — used to exercise budgets/cancellation."""

    name = "slow"

    def __init__(self, inner: Any, delay: float = 0.05) -> None:
        self.inner = inner
        self.delay = delay

    def complete(self, messages: Sequence[Message], **kwargs: Any) -> LLMResponse:
        time.sleep(self.delay)
        return self.inner.complete(messages, **kwargs)


@contextlib.contextmanager
def temp_workspace(prefix: str = "deepresearch-test-") -> Iterator[str]:
    """A throwaway directory that is intentionally never deleted.

    Some sandboxes refuse ``chmod``/``rmtree`` on temp paths; leaving a few KB
    behind in the OS temp folder is harmless and keeps the suite portable.
    """
    path = temp_dir()
    try:
        yield path
    finally:
        pass
