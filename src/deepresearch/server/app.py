"""Standard-library HTTP server that powers the DeepResearch web UI.

The server is deliberately small and dependency-free: a ``ThreadingHTTPServer``
serves the static single-page app, a small JSON API (health / config / runs) and
``POST /api/research``.  The research itself runs in a background thread while
the request thread forwards every :class:`~deepresearch.events.ProgressEvent`
to the browser as Server-Sent Events, ending with ``event: result``.

Only the Python standard library is used (``http.server``, ``json``, ``queue``,
``threading``) so the whole UI works offline, without a build step and without
any third-party web framework.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import uuid
import webbrowser
from collections import OrderedDict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlsplit

from .. import __version__
from ..config import Settings
from ..events import ProgressEvent
from ..models import Depth, to_jsonable

logger = logging.getLogger(__name__)

#: Root directory that holds ``index.html`` / ``style.css`` / ``app.js``.
STATIC_DIR = Path(__file__).resolve().parent / "static"

#: Request bodies for ``POST /api/research`` are capped at 8 KiB.
MAX_BODY_BYTES = 8 * 1024

#: How many finished runs stay queryable through ``/api/runs``.
MAX_RUNS = 20

#: Idle SSE streams get a comment line this often to keep proxies awake.
SSE_PING_SECONDS = 10.0

#: Explicit extension -> content-type map (no ``mimetypes`` registry lookups).
_CONTENT_TYPES: Dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}

_SOCKET_ERRORS = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)


def _now() -> str:
    """Current UTC time as an ISO-8601 string (second precision)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_run_id() -> str:
    """Readable, collision-resistant run id: ``20261026T164611-1a2b3c4d``."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def _json_bytes(payload: Any) -> bytes:
    """Serialise JSON as UTF-8 without ASCII escaping (readable Chinese)."""
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class RunRegistry:
    """In-memory ring buffer of the most recent completed runs (newest first)."""

    def __init__(self, limit: int = MAX_RUNS) -> None:
        self._limit = max(1, int(limit))
        self._lock = threading.Lock()
        self._runs: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()

    def add(self, record: Dict[str, Any]) -> None:
        with self._lock:
            run_id = str(record["id"])
            self._runs[run_id] = record
            self._runs.move_to_end(run_id)
            while len(self._runs) > self._limit:
                self._runs.popitem(last=False)

    def get(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._runs.get(run_id)

    def summaries(self) -> List[Dict[str, Any]]:
        """Public list payload (newest first, secrets and bodies stripped)."""
        with self._lock:
            records = list(self._runs.values())
        records.reverse()
        keys = ("id", "question", "title", "created_at", "markdown_path")
        return [{key: record.get(key) for key in keys} for record in records]

    def __len__(self) -> int:
        with self._lock:
            return len(self._runs)


class _EventRelay:
    """Adapter collecting pipeline events for one SSE response.

    ``run_research`` accepts an :class:`~deepresearch.events.EventSink` but
    mirrors progress by calling a single-argument ``emit(event)`` handler.
    Accepting both that shape and the usual ``emit(type, message, ...)`` shape
    keeps the stream working regardless of how the API layer wires its sink.
    """

    def __init__(self) -> None:
        self.queue: "queue.Queue[tuple[str, Any]]" = queue.Queue()

    def emit(
        self,
        event: Any,
        message: Optional[str] = None,
        *,
        data: Optional[Dict[str, Any]] = None,
        percent: Optional[float] = None,
    ) -> None:
        if isinstance(event, ProgressEvent):
            progress = event
        elif isinstance(event, str) or hasattr(event, "value"):
            event_type = getattr(event, "value", event)
            progress = ProgressEvent(
                type=str(event_type),
                message=message or "",
                data=dict(data or {}),
                percent=percent,
            )
        else:
            return
        self.queue.put(("progress", progress.to_dict()))


def _build_record(
    run_id: str,
    question: str,
    result: Any,
    created_at: str,
) -> Dict[str, Any]:
    """Snapshot a :class:`~deepresearch.models.RunResult` for the API/registry."""
    report = result.report
    markdown = report.markdown or ""
    usage = to_jsonable(result.usage)
    source_count = len(report.references or [])
    record: Dict[str, Any] = {
        "id": run_id,
        "question": report.question or question,
        "title": report.title or question,
        "created_at": created_at,
        "generated_at": report.generated_at,
        "language": report.language,
        "markdown": markdown,
        "markdown_path": result.markdown_path,
        "json_path": result.json_path,
        "trace_path": result.trace_path,
        "usage": usage,
        "source_count": source_count,
        "summary": report.summary or "",
        "key_takeaways": list(report.key_takeaways or []),
        "limitations": list(report.limitations or []),
    }
    record["result_json"] = {
        "run_id": run_id,
        "question": record["question"],
        "title": record["title"],
        "language": record["language"],
        "created_at": created_at,
        "generated_at": report.generated_at,
        "summary": record["summary"],
        "key_takeaways": record["key_takeaways"],
        "limitations": record["limitations"],
        "markdown": markdown,
        "usage": usage,
        "source_count": source_count,
        "markdown_path": result.markdown_path,
        "json_path": result.json_path,
        "report": to_jsonable(report),
    }
    return record


def _result_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    """``event: result`` data: everything the UI needs to render one report."""
    run_id = record["id"]
    return {
        "run_id": run_id,
        "title": record["title"],
        "markdown": record["markdown"],
        "usage": record["usage"],
        "source_count": record["source_count"],
        "report_url": f"/api/runs/{run_id}/report.md",
        "json_url": f"/api/runs/{run_id}/result.json",
        "question": record["question"],
        "language": record["language"],
        "created_at": record["created_at"],
        "summary": record["summary"],
        "key_takeaways": record["key_takeaways"],
        "limitations": record["limitations"],
    }


class DeepResearchHTTPServer(ThreadingHTTPServer):
    """Threading HTTP server carrying the per-instance settings and run registry."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: Any,
        handler: Any,
        *,
        settings: Settings,
        registry: RunRegistry,
        static_dir: Path,
        out_dir: Optional[str],
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.static_dir = Path(static_dir)
        self.out_dir = out_dir
        super().__init__(server_address, handler)

    def handle_error(self, request: Any, client_address: Any) -> None:
        # Disconnects are normal (browser tab closed, SSE cancelled); keep quiet.
        logger.debug("connection error from %s", client_address, exc_info=True)


class DeepResearchRequestHandler(BaseHTTPRequestHandler):
    """Routes for the static UI, the JSON API and the SSE research stream."""

    server_version = f"DeepResearch/{__version__}"
    protocol_version = "HTTP/1.1"

    # -- dispatch ---------------------------------------------------------- #
    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        self._safe(self._route_get)

    def do_HEAD(self) -> None:  # noqa: N802 - http.server naming
        self._safe(self._route_head)

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        self._safe(self._route_post)

    def _safe(self, action: Any) -> None:
        self._started_response = False
        self._send_ok_headers_only = False
        try:
            action()
        except _SOCKET_ERRORS:
            self.close_connection = True
        except Exception as exc:  # noqa: BLE001 - last-resort JSON error reply
            logger.exception("request failed: %s %s", self.command, self.path)
            self.close_connection = True
            if not self._started_response:
                try:
                    self._send_json(500, {"ok": False, "error": f"internal error: {exc}"})
                except Exception:  # pragma: no cover - socket already gone
                    pass

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        logger.debug("%s - %s", self.address_string(), fmt % args)

    # -- GET --------------------------------------------------------------- #
    def _route_get(self) -> None:
        path = urlsplit(self.path).path
        if path in ("/", "/index.html"):
            self._serve_static("index.html")
        elif path.startswith("/static/"):
            self._serve_static(unquote(path[len("/static/") :]))
        elif path == "/api/health":
            public = self._settings().public_dict()
            self._send_json(
                200,
                {
                    "ok": True,
                    "version": __version__,
                    "offline": bool(public.get("offline")),
                },
            )
        elif path == "/api/config":
            self._send_json(200, self._settings().public_dict())
        elif path == "/api/runs":
            self._send_json(200, {"runs": self._server().registry.summaries()})
        elif path.startswith("/api/runs/"):
            self._route_run_file(path)
        else:
            self._send_json(404, {"ok": False, "error": "not found"})

    def _route_head(self) -> None:
        # A tiny, well-behaved HEAD: same status/headers as GET, no body.
        self._send_ok_headers_only = True
        self._route_get()

    def _serve_static(self, relative: str) -> None:
        """Serve one file from ``static/``; ``..`` and absolute paths get 404."""
        static_dir = self._server().static_dir.resolve()
        relative = unquote(relative or "").replace("\\", "/").strip()
        if not relative or relative.endswith("/"):
            relative += "index.html"
        parts = [part for part in relative.split("/") if part not in ("", ".")]
        unsafe = (
            not parts
            or any(part == ".." for part in parts)
            or relative.startswith("/")
            or ":" in parts[0]
        )
        if unsafe:
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        target = static_dir.joinpath(*parts).resolve()
        try:
            target.relative_to(static_dir)
        except ValueError:
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        if not target.is_file():
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        content_type = _CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")
        self._send_bytes(200, content_type, target.read_bytes())

    # -- POST -------------------------------------------------------------- #
    def _route_post(self) -> None:
        path = urlsplit(self.path).path
        if path != "/api/research":
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        payload = self._read_json_body()
        if payload is None:
            return
        question = payload.get("question")
        if not isinstance(question, str) or not question.strip():
            self._send_json(
                400,
                {
                    "ok": False,
                    "error": "question is required and must be a non-empty string",
                },
            )
            return
        question = question.strip()

        depth_value = payload.get("depth")
        depth: Optional[str] = None
        if depth_value not in (None, ""):
            try:
                depth = Depth.parse(depth_value).value
            except ValueError as exc:
                self._send_json(400, {"ok": False, "error": str(exc)})
                return

        language_value = payload.get("language")
        language: Optional[str] = None
        if language_value not in (None, ""):
            language = "en" if str(language_value).strip().lower().startswith("en") else "zh"
        self._stream_research(question, depth, language)

    def _read_json_body(self) -> Optional[Dict[str, Any]]:
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or 0)
        except ValueError:
            # The body length is unknown, so the connection cannot be reused.
            self.close_connection = True
            self._send_json(400, {"ok": False, "error": "invalid Content-Length"})
            return None
        if length <= 0:
            self._send_json(400, {"ok": False, "error": "empty request body"})
            return None
        if length > MAX_BODY_BYTES:
            # Drain nothing: the oversized body stays unread, so close the socket.
            self.close_connection = True
            self._send_json(
                413,
                {
                    "ok": False,
                    "error": f"request body too large (max {MAX_BODY_BYTES} bytes)",
                },
            )
            return None
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._send_json(400, {"ok": False, "error": f"invalid JSON: {exc}"})
            return None
        if not isinstance(payload, dict):
            self._send_json(400, {"ok": False, "error": "JSON body must be an object"})
            return None
        return payload

    # -- research + SSE ---------------------------------------------------- #
    def _stream_research(
        self, question: str, depth: Optional[str], language: Optional[str]
    ) -> None:
        """Run research in a worker thread and relay its events over SSE."""
        server = self._server()
        relay = _EventRelay()
        events = relay.queue
        run_id = _new_run_id()
        created_at = _now()

        def worker() -> None:
            try:
                # Imported lazily so the server starts (and tests health/config)
                # even while the research pipeline is still being assembled.
                from ..api import run_research

                result = run_research(
                    question,
                    settings=server.settings,
                    depth=depth,
                    language=language,
                    out_dir=server.out_dir,
                    events=relay,
                    save=True,
                )
                record = _build_record(run_id, question, result, created_at)
                server.registry.add(record)
                events.put(("result", record))
            except Exception as exc:  # noqa: BLE001 - surfaced to the browser
                logger.exception("research run %s failed", run_id)
                message = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
                events.put(("error", message))

        threading.Thread(target=worker, name=f"deepresearch-{run_id}", daemon=True).start()

        started = False
        try:
            self._begin_sse()
            started = True
            while True:
                try:
                    kind, payload = events.get(timeout=SSE_PING_SECONDS)
                except queue.Empty:
                    self._write_sse_comment("keep-alive")
                    continue
                if kind == "progress":
                    self._write_sse_event("progress", payload)
                elif kind == "result":
                    self._write_sse_event("result", _result_payload(payload))
                    break
                else:
                    self._write_sse_event(
                        "error",
                        {"type": "error", "message": str(payload), "at": _now()},
                    )
                    break
        except _SOCKET_ERRORS:
            logger.info("client disconnected from run %s", run_id)
            self.close_connection = True
        finally:
            if started:
                try:
                    self._end_sse()
                except OSError:  # broken pipe / reset: nothing left to flush to
                    self.close_connection = True

    def _begin_sse(self) -> None:
        self._started_response = True
        self.close_connection = False
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

    def _write_sse_event(self, event_name: str, payload: Any) -> None:
        data = json.dumps(payload, ensure_ascii=False)
        self._write_chunk(f"event: {event_name}\ndata: {data}\n\n")

    def _write_sse_comment(self, text: str) -> None:
        self._write_chunk(f": {text}\n\n")

    def _write_chunk(self, text: str) -> None:
        body = text.encode("utf-8")
        if not body:
            return
        self.wfile.write(f"{len(body):x}\r\n".encode("ascii") + body + b"\r\n")
        self.wfile.flush()

    def _end_sse(self) -> None:
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    # -- run downloads ----------------------------------------------------- #
    def _route_run_file(self, path: str) -> None:
        rest = path[len("/api/runs/") :]
        registry = self._server().registry
        if rest.endswith("/report.md"):
            run_id = unquote(rest[: -len("/report.md")]).strip("/")
            record = registry.get(run_id) if run_id and "/" not in run_id else None
            if record is None:
                self._send_json(404, {"ok": False, "error": "run not found"})
                return
            text = record.get("markdown") or ""
            if not text:
                text = self._read_file(record.get("markdown_path"))
            if not text:
                self._send_json(404, {"ok": False, "error": "report is not available"})
                return
            self._send_bytes(200, "text/markdown; charset=utf-8", text.encode("utf-8"))
            return
        if rest.endswith("/result.json"):
            run_id = unquote(rest[: -len("/result.json")]).strip("/")
            record = registry.get(run_id) if run_id and "/" not in run_id else None
            if record is None:
                self._send_json(404, {"ok": False, "error": "run not found"})
                return
            payload = record.get("result_json")
            if payload is None:
                raw = self._read_file(record.get("json_path"))
                if raw:
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        payload = None
            if payload is None:
                self._send_json(404, {"ok": False, "error": "result is not available"})
                return
            self._send_json(200, payload)
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    @staticmethod
    def _read_file(path: Optional[str]) -> str:
        if not path:
            return ""
        file = Path(path)
        try:
            if file.is_file():
                return file.read_text(encoding="utf-8")
        except OSError:
            logger.debug("cannot read %s", path, exc_info=True)
        return ""

    # -- response helpers -------------------------------------------------- #
    def _settings(self) -> Settings:
        return self._server().settings

    def _server(self) -> DeepResearchHTTPServer:
        return self.server

    def _send_json(self, status: int, payload: Any) -> None:
        self._send_bytes(
            status,
            "application/json; charset=utf-8",
            _json_bytes(payload),
            cache_control="no-store",
        )

    def _send_bytes(
        self,
        status: int,
        content_type: str,
        body: bytes,
        *,
        cache_control: str = "no-cache",
    ) -> None:
        self._started_response = True
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if not getattr(self, "_send_ok_headers_only", False):
            self.wfile.write(body)


def create_server(
    settings: Settings,
    host: str = "127.0.0.1",
    port: int = 0,
    *,
    out_dir: Optional[str] = None,
) -> ThreadingHTTPServer:
    """Create (but do not start) the DeepResearch web server.

    ``port=0`` lets the operating system pick a free port; the actual address is
    available as ``server.server_address``.  Pass ``out_dir`` to override where
    reports are saved for this server instance.
    """
    return DeepResearchHTTPServer(
        (host, int(port)),
        DeepResearchRequestHandler,
        settings=settings,
        registry=RunRegistry(),
        static_dir=STATIC_DIR,
        out_dir=out_dir,
    )


def serve(
    settings: Settings,
    host: str = "127.0.0.1",
    port: int = 8000,
    *,
    open_browser: bool = False,
) -> None:
    """Create the server and block serving requests until interrupted.

    The CLI prints the banner, URL and provider summary; this function only owns
    the blocking serve loop (plus optional browser launch), so it can also be
    embedded.  ``Ctrl+C`` shuts the server down cleanly.
    """
    settings.validate()  # fail fast for programmatic callers
    httpd = create_server(settings, host, port)
    actual_port = int(httpd.server_address[1])
    if open_browser:
        display_host = "127.0.0.1" if host in ("", "0.0.0.0", "::") else host
        url = f"http://{display_host}:{actual_port}/"
        timer = threading.Timer(0.5, lambda: webbrowser.open(url))
        timer.daemon = True
        timer.start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
