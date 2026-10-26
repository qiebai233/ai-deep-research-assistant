"""Public one-call API: ``run_research(question)``.

This module is the seam between the CLI / web server and the agent pipeline.  It
owns configuration resolution, warning emission and artefact persistence, so the
orchestrator stays a pure research engine and both interfaces behave identically.
"""

from __future__ import annotations

from typing import Any, Optional

from .config import Settings
from .errors import ConfigError
from .events import EventSink, EventType
from .models import RunResult
from .storage import save_run

__all__ = ["run_research"]


def run_research(
    question: str,
    *,
    settings: Optional[Settings] = None,
    depth: Optional[str] = None,
    language: Optional[str] = None,
    out_dir: Optional[str] = None,
    events: Optional[EventSink] = None,
    save: bool = True,
    llm: Any = None,
    search: Any = None,
    fetcher: Any = None,
) -> RunResult:
    """Research ``question`` end-to-end and return the full run result.

    Parameters
    ----------
    question:
        The research question. Must not be blank.
    settings:
        Resolved :class:`~deepresearch.config.Settings`; defaults to
        ``Settings.from_env()`` (``.env`` + environment variables).
    depth / language:
        Per-run overrides of ``settings.depth`` / ``settings.language``.
    out_dir:
        Where artefacts are written; defaults to ``settings.out_dir``.
    events:
        Optional :class:`~deepresearch.events.EventSink` (or any object with an
        ``emit`` method) receiving live progress events.
    save:
        Write ``report.md`` / ``result.json`` / ``trace.jsonl`` when true.
    llm / search / fetcher:
        Provider overrides, mainly for tests and embedding.

    Raises
    ------
    ConfigError
        Empty question or invalid configuration (missing key, bad provider, ...).
    """
    question = (question or "").strip()
    if not question:
        raise ConfigError("research question must not be empty")
    if len(question) > 2000:
        raise ConfigError("research question is too long (max 2000 characters)")

    resolved = settings or Settings.from_env()
    if depth is not None:
        resolved = resolved.with_overrides(depth=depth)
    if language is not None:
        resolved = resolved.with_overrides(language=language)
    warnings = resolved.validate()

    # The orchestrator emits into ``sink``; every event is mirrored to the caller
    # and kept in memory so it can be written to trace.jsonl.
    sink = EventSink(keep_history=True)
    if events is not None:
        if hasattr(events, "emit"):
            # EventSink.emit accepts a ready-made ProgressEvent, so a sink can be
            # used directly as a handler (it keeps its own history and fan-out).
            sink.subscribe(events.emit)  # type: ignore[union-attr]
        elif callable(events):
            sink.subscribe(events)  # type: ignore[arg-type]

    for warning in warnings:
        sink.emit(EventType.WARNING, warning)

    from .agent.orchestrator import Orchestrator

    orchestrator = Orchestrator(resolved, llm=llm, search=search, fetcher=fetcher, events=sink)
    result = orchestrator.run(question, depth=depth, language=language)

    if save:
        save_run(
            result,
            out_dir or resolved.out_dir,
            settings=resolved,
            trace_events=sink.history,
            want_json=resolved.report_json,
            want_trace=resolved.report_trace,
        )
    return result
