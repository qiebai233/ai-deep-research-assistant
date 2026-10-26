#!/usr/bin/env python
"""Run the whole test suite without installing the package.

Usage::

    python run_tests.py                  # run every test
    python run_tests.py -k agent         # only test ids containing "agent"
    python run_tests.py -v --failfast
    python run_tests.py tests.test_cli   # run one module

This is the canonical entry point in CI *and* for local development: it puts
``src/`` on ``sys.path`` so no virtualenv / editable install is required.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    os.environ.setdefault("PYTHONHASHSEED", "0")
    sys.path.insert(0, str(SRC))
    sys.path.insert(0, str(ROOT))

    verbosity = 2
    pattern = "test_*.py"
    failfast = False
    modules: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in ("-v", "--verbose"):
            verbosity = 2
            index += 1
        elif arg in ("-q", "--quiet"):
            verbosity = 1
            index += 1
        elif arg in ("-f", "--failfast"):
            failfast = True
            index += 1
        elif arg == "-k" and index + 1 < len(args):
            pattern = args[index + 1]
            index += 2
        elif arg.startswith("-k=") or (arg.startswith("-k") and len(arg) > 2):
            pattern = arg.split("=", 1)[1] if arg.startswith("-k=") else arg[2:]
            index += 1
        elif not arg.startswith("-"):
            modules.append(arg)
            index += 1
        else:
            print(f"unknown option: {arg}", file=sys.stderr)
            return 2

    loader = unittest.TestLoader()
    if modules:
        suite = loader.loadTestsFromNames(modules)
    else:
        if pattern != "test_*.py":
            loader.testNamePatterns = [f"*{pattern}*"]
        suite = loader.discover(str(ROOT / "tests"), pattern="test_*.py", top_level_dir=str(ROOT))
    runner = unittest.TextTestRunner(verbosity=verbosity, failfast=failfast)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
