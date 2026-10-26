"""Verify every relative Markdown link/image target exists (docs quality gate)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)")
SKIP_PREFIX = ("http://", "https://", "mailto:", "#", "data:")

problems = []
checked = 0
for md in ROOT.rglob("*.md"):
    if any(part in {".git", ".test-tmp", "_sample", "tmp"} for part in md.parts):
        continue
    text = md.read_text(encoding="utf-8", errors="replace")
    for target in LINK_RE.findall(text):
        if target.startswith(SKIP_PREFIX):
            continue
        path_part = target.split("#", 1)[0]
        if not path_part:
            continue
        if path_part.startswith("/"):
            candidate = ROOT / path_part.lstrip("/")
        else:
            candidate = (md.parent / path_part).resolve()
        checked += 1
        if not candidate.exists():
            problems.append(f"{md.relative_to(ROOT)} -> {target}")

print(f"checked {checked} relative links in {len(list(ROOT.rglob('*.md')))} markdown files")
if problems:
    print("BROKEN:")
    for item in problems:
        print(" -", item)
    sys.exit(1)
print("all relative links resolve")
