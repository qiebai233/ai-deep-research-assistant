"""Dependency-free web interface for DeepResearch.

The public surface is deliberately tiny::

    from deepresearch.server import create_server, serve

    server = create_server(settings, port=0)   # bound, not started
    server.serve_forever()

``serve`` is the blocking convenience wrapper used by ``deepresearch serve``.
"""

from __future__ import annotations

from .app import (
    MAX_BODY_BYTES,
    MAX_RUNS,
    STATIC_DIR,
    DeepResearchHTTPServer,
    RunRegistry,
    create_server,
    serve,
)

__all__ = [
    "MAX_BODY_BYTES",
    "MAX_RUNS",
    "STATIC_DIR",
    "DeepResearchHTTPServer",
    "RunRegistry",
    "create_server",
    "serve",
]
