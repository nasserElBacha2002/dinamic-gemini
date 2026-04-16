#!/usr/bin/env python3
"""
Stage 1 — List v3 API routes that inject repositories via FastAPI Depends(get_*_repo).

Read-only report for cleanup planning. Does not modify code.
Run from repo root or backend/:

  python3 scripts/report_v3_route_repository_usage.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    routes_dir = Path(__file__).resolve().parents[1] / "src" / "api" / "routes" / "v3"
    if not routes_dir.is_dir():
        print(f"Expected v3 routes directory missing: {routes_dir}", file=sys.stderr)
        return 2

    pattern = re.compile(
        r"^\s*(\w+)\s*:\s*\w+\s*=\s*Depends\((get_\w+_repo)\)",
        re.MULTILINE,
    )

    print("v3 route repository injections (Depends(get_*_repo))")
    print("=" * 72)
    any_hits = False
    for path in sorted(routes_dir.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        hits = list(pattern.finditer(text))
        if not hits:
            continue
        any_hits = True
        print(f"\n{path.name}")
        for m in hits:
            param = m.group(1)
            dep = m.group(2)
            line_no = text[: m.start()].count("\n") + 1
            print(f"  L{line_no}: {param} = Depends({dep})")

    if not any_hits:
        print("\n(no matches — pattern may need updating)")
    else:
        print("\nSuggested next refactors (Stage 2+)")
        print("- Replace each Depends(get_*_repo) with a dedicated query/command use case.")
        print("- Keep routes thin: parse/validate → use case → map errors → response.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
