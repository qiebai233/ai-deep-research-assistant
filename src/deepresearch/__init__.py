"""DeepResearch — an autonomous, citation-grounded deep-research agent.

Typical use::

    from deepresearch import run_research

    result = await run_research("固态电池 2025 年产业化进展", depth="deep")
    print(result.report.markdown)

The heavy lifting lives in :mod:`deepresearch.api`; this module only exposes the
public surface and keeps imports lazy so that ``import deepresearch`` stays fast
and dependency-free.
"""

from __future__ import annotations

from typing import Any

from .models import Depth, Report, ResearchState, RunResult, UsageStats

__version__ = "0.1.0"
__all__ = [
    "__version__",
    "Depth",
    "Report",
    "ResearchState",
    "RunResult",
    "UsageStats",
    "run_research",
]


def __getattr__(name: str) -> Any:  # pragma: no cover - thin lazy facade
    if name == "run_research":
        from .api import run_research

        return run_research
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
