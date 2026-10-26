"""Progress events: the single observability channel of a research run.

The CLI renders them with Rich, the web UI forwards them over Server-Sent
Events, and tests collect them to assert that the pipeline reached a stage.
Emitting an event must never break a run, hence :meth:`EventSink.emit`
swallows listener exceptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .models import utcnow


class EventType(str, Enum):
    RUN_START = "run_start"
    PLAN_READY = "plan_ready"
    SEARCH_START = "search_start"
    SEARCH_DONE = "search_done"
    FETCH_START = "fetch_start"
    SOURCE_READY = "source_ready"
    FINDINGS_READY = "findings_ready"
    GAP_FOUND = "gap_found"
    ROUND_START = "round_start"
    OUTLINE_READY = "outline_ready"
    SECTION_READY = "section_ready"
    REPORT_READY = "report_ready"
    RUN_END = "run_end"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class ProgressEvent:
    type: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    percent: Optional[float] = None
    at: str = field(default_factory=utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "message": self.message,
            "data": self.data,
            "percent": self.percent,
            "at": self.at,
        }


EventHandler = Callable[[ProgressEvent], None]


class EventSink:
    """Fan-out for progress events, with optional history for the API/tests."""

    def __init__(
        self,
        handlers: Optional[List[EventHandler]] = None,
        keep_history: bool = False,
        history_limit: int = 500,
    ) -> None:
        self._handlers: List[EventHandler] = list(handlers or [])
        self._keep_history = keep_history
        self._history_limit = history_limit
        self.history: List[ProgressEvent] = []

    def subscribe(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    @property
    def handlers(self) -> List[EventHandler]:
        """Read-only view of the registered handlers (used for bridging sinks)."""
        return list(self._handlers)

    def emit(
        self,
        event_type: Any,
        message: Optional[str] = None,
        *,
        data: Optional[Dict[str, Any]] = None,
        percent: Optional[float] = None,
    ) -> ProgressEvent:
        """Emit a new event, or forward an existing :class:`ProgressEvent`.

        Accepting a ready-made event as the only argument makes ``sink.emit``
        usable directly as an :data:`EventHandler`, which is how nested sinks
        (public API -> web UI / CLI) are bridged.
        """
        if isinstance(event_type, ProgressEvent):
            event = event_type
        else:
            event = ProgressEvent(
                type=event_type.value if isinstance(event_type, EventType) else str(event_type),
                message=message or "",
                data=data or {},
                percent=percent,
            )
        if self._keep_history:
            self.history.append(event)
            if len(self.history) > self._history_limit:
                del self.history[: len(self.history) - self._history_limit]
        for handler in list(self._handlers):
            try:
                handler(event)
            except Exception:  # pragma: no cover - listeners must never break a run
                continue
        return event
