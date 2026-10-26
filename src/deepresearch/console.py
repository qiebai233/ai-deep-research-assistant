"""Tiny ANSI terminal layer (stdlib only) used by the CLI.

Deliberately small: colour helpers, a few symbols, a word-wrapped event line
renderer, a ruled banner and a column table.  ``NO_COLOR`` and non-TTY output
are handled automatically, so piping the CLI into a file stays clean.
"""

from __future__ import annotations

import os
import shutil
import sys
import textwrap
from typing import Iterable, Sequence, TextIO

_RESET = "\033[0m"
_STYLES = {
    "bold": "\033[1m",
    "dim": "\033[2m",
    "italic": "\033[3m",
    "underline": "\033[4m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "gray": "\033[90m",
    "bright_green": "\033[92m",
    "bright_cyan": "\033[96m",
}

SYMBOLS = {
    "ok": "✓",
    "fail": "✗",
    "warn": "!",
    "step": "→",
    "bullet": "•",
    "dot": "·",
    "bar": "─",
}

#: Event type -> (symbol, colour) for the live research log.
EVENT_STYLE = {
    "run_start": ("▶", "bold"),
    "plan_ready": ("◈", "cyan"),
    "search_start": ("⌕", "dim"),
    "search_done": ("⌕", "dim"),
    "fetch_start": ("↓", "dim"),
    "source_ready": ("✓", "green"),
    "findings_ready": ("◈", "cyan"),
    "gap_found": ("?", "yellow"),
    "round_start": ("↻", "dim"),
    "outline_ready": ("☰", "cyan"),
    "section_ready": ("✎", "dim"),
    "report_ready": ("★", "bright_green"),
    "run_end": ("■", "bold"),
    "warning": ("!", "yellow"),
    "error": ("✗", "red"),
}


def supports_color(stream: TextIO | None = None) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    stream = stream or sys.stdout
    return bool(getattr(stream, "isatty", lambda: False)())


class Console:
    """Small, dependency-free console helper."""

    def __init__(
        self,
        stream: TextIO | None = None,
        *,
        color: bool | None = None,
        quiet: bool = False,
        width: int | None = None,
    ) -> None:
        self.stream = stream or sys.stdout
        self.use_color = supports_color(self.stream) if color is None else color
        self.quiet = quiet
        self.width = width or shutil.get_terminal_size((88, 24)).columns

    # -- primitives -------------------------------------------------------- #
    def style(self, text: str, *styles: str) -> str:
        if not self.use_color or not styles:
            return text
        prefix = "".join(_STYLES[s] for s in styles if s in _STYLES)
        return f"{prefix}{text}{_RESET}" if prefix else text

    def write(self, text: str = "") -> None:
        self.stream.write(text)
        self.stream.flush()

    def line(self, text: str = "") -> None:
        if not self.quiet:
            self.write(text + "\n")

    # -- semantic output --------------------------------------------------- #
    def info(self, message: str) -> None:
        self.line(f"{self.style('·', 'dim')} {message}")

    def ok(self, message: str) -> None:
        self.line(f"{self.style(SYMBOLS['ok'], 'green')} {message}")

    def warn(self, message: str) -> None:
        self.line(f"{self.style(SYMBOLS['warn'], 'yellow')} {self.style(message, 'yellow')}")

    def error(self, message: str) -> None:
        self.line(f"{self.style(SYMBOLS['fail'], 'red')} {self.style(message, 'red')}")

    def step(self, message: str) -> None:
        self.line(f"{self.style(SYMBOLS['step'], 'cyan')} {message}")

    def heading(self, message: str) -> None:
        self.line()
        self.line(self.style(message, "bold"))

    def rule(self, title: str = "") -> None:
        if title:
            title = f" {title} "
            side = (self.width - len(title) - 2) // 2
            line = SYMBOLS["bar"] * max(0, side) + title + SYMBOLS["bar"] * max(0, side)
            self.line(self.style(line, "dim"))
        else:
            self.line(self.style(SYMBOLS["bar"] * min(self.width, 88), "dim"))

    def banner(self, version: str) -> None:
        self.line()
        self.line(self.style("  DeepResearch", "bold", "cyan") + self.style(f"  v{version}", "dim"))
        self.line(self.style("  AI 深度调研助手 · 给定问题，自动调研并生成带引用的报告", "dim"))
        self.line()

    def kv(self, pairs: Iterable[tuple[str, str]], indent: str = "  ") -> None:
        pairs = list(pairs)
        if not pairs:
            return
        width = max(len(label) for label, _ in pairs)
        for label, value in pairs:
            self.line(f"{indent}{self.style(label.ljust(width), 'dim')}  {value}")

    def table(self, headers: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
        if not rows:
            return
        columns = len(headers)
        widths = [len(h) for h in headers]
        for row in rows:
            for i in range(columns):
                widths[i] = max(widths[i], len(str(row[i])) if i < len(row) else 0)
        header = "  ".join(
            self.style(str(headers[i]).ljust(widths[i]), "bold") for i in range(columns)
        )
        self.line(header)
        self.line(self.style("  ".join("─" * w for w in widths), "dim"))
        for row in rows:
            cells = []
            for i in range(columns):
                value = str(row[i]) if i < len(row) else ""
                cells.append(value.ljust(widths[i]))
            self.line("  ".join(cells))

    # -- live progress ----------------------------------------------------- #
    def event(self, sequence: int, event) -> None:
        """Render one :class:`~deepresearch.events.ProgressEvent`."""
        if self.quiet:
            return
        symbol, colour = EVENT_STYLE.get(event.type, ("·", ""))
        percent = ""
        if event.percent is not None:
            percent = self.style(f"{event.percent:>3.0f}% ", "dim")
        message = event.message
        if event.type == "section_ready":
            message = self.style(message, "dim")
        self.line(f"  {percent}{self.style(symbol, colour)} {message}")

    def event_text(self, event) -> str:
        """One-line text form (used for logs and tests)."""
        symbol, _ = EVENT_STYLE.get(event.type, ("·", ""))
        suffix = f" [{event.percent:>3.0f}%]" if event.percent is not None else ""
        return f"{symbol} {event.message}{suffix}"

    def wrap(self, text: str, indent: str = "  ") -> None:
        for paragraph in str(text).splitlines() or [""]:
            if not paragraph.strip():
                self.line()
                continue
            for chunk in textwrap.wrap(paragraph, width=max(20, self.width - len(indent))) or [""]:
                self.line(indent + chunk)
