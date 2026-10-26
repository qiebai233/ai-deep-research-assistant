"""Persisting a research run.

A run produces three artefacts inside one timestamped directory::

    reports/20261026-164500-固态电池产业化进展/
        report.md     # the human-facing deliverable
        result.json   # full machine-readable record (report + state + usage)
        trace.jsonl   # one JSON object per progress event (debug / replay)

Everything is UTF-8 and newline-normalised so a report looks identical on
Windows, macOS and Linux.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .events import ProgressEvent
from .models import RunResult, to_jsonable

__all__ = ["save_run", "slugify", "run_directory"]

_SLUG_KEEP = re.compile(r"[^0-9a-zA-Z\u4e00-\u9fff\u3400-\u4dbf]+")


def slugify(text: str, *, max_len: int = 40, fallback: str = "research") -> str:
    """Filesystem- and URL-friendly slug that keeps CJK characters readable."""
    normalised = unicodedata.normalize("NFKC", text or "").strip()
    slug = _SLUG_KEEP.sub("-", normalised).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug:
        return fallback
    if len(slug) > max_len:
        cut = slug[:max_len].rstrip("-")
        slug = cut or fallback
    return slug


def run_directory(out_dir: str | Path, question: str) -> Path:
    """Create and return ``{out_dir}/{YYYYmmdd-HHMMSS}-{slug}``."""
    base = Path(out_dir).expanduser()
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # pragma: no cover - permission problems
        raise OSError(f"cannot create report directory {base}: {exc}") from exc
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    directory = base / f"{stamp}-{slugify(question)}"
    suffix = 2
    while directory.exists():
        directory = base / f"{stamp}-{slugify(question)}-{suffix}"
        suffix += 1
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def save_run(
    result: RunResult,
    out_dir: str | Path,
    *,
    settings: Any = None,
    trace_events: Optional[Sequence[ProgressEvent]] = None,
    want_json: bool = True,
    want_trace: bool = True,
) -> RunResult:
    """Write ``report.md`` (+ optional ``result.json`` / ``trace.jsonl``).

    The passed :class:`~deepresearch.models.RunResult` is updated in place with
    ``out_dir`` and the artefact paths, and returned for convenience.
    """
    report = result.report
    directory = run_directory(out_dir, report.question)

    markdown_path = directory / "report.md"
    if not report.markdown:
        from .report.renderer import render_markdown

        report.markdown = render_markdown(report)
    _write_text(markdown_path, report.markdown)

    result.out_dir = str(directory)
    result.markdown_path = str(markdown_path)

    if want_json:
        payload: Dict[str, Any] = {
            "schema_version": 1,
            "generator": "DeepResearch",
            "version": _version(),
            "question": report.question,
            "generated_at": report.generated_at,
            "usage": to_jsonable(result.usage or report.usage),
            "report": to_jsonable(report),
            "state": to_jsonable(result.state),
        }
        if settings is not None:
            payload["settings"] = settings.public_dict()
        json_path = directory / "result.json"
        _write_text(json_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        result.json_path = str(json_path)

    if want_trace and trace_events:
        trace_path = directory / "trace.jsonl"
        lines: List[str] = []
        for event in trace_events:
            record = event.to_dict() if isinstance(event, ProgressEvent) else dict(event)
            lines.append(json.dumps(record, ensure_ascii=False))
        _write_text(trace_path, "\n".join(lines) + "\n")
        result.trace_path = str(trace_path)

    return result


def _version() -> str:  # pragma: no cover - trivial indirection for patching
    from . import __version__

    return __version__
