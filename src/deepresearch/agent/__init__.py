"""Agent pipeline: planning, research, writing and orchestration.

The only supported public entry point is :class:`Orchestrator`.
"""

from __future__ import annotations

from .orchestrator import Orchestrator

__all__ = ["Orchestrator"]
