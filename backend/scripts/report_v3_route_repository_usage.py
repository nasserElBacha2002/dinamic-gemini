#!/usr/bin/env python3
"""
List v3 API routes that inject repositories via FastAPI Depends(get_*_repo).

Read-only report for cleanup planning (Phase 1+). Does not modify application code.
Run from repo root or backend/:

  python3 scripts/report_v3_route_repository_usage.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def _route_and_handler_before(text: str, pos: int) -> tuple[str, str]:
    """Best-effort: last @router.METHOD("path") before pos, and first def name after it."""
    before = text[:pos]
    router_matches = list(
        re.finditer(
            r'@router\.(get|post|put|patch|delete)\(\s*(["\'])([^"\']+)\2',
            before,
            re.IGNORECASE,
        )
    )
    if not router_matches:
        return "", ""
    rm = router_matches[-1]
    route_str = f"{rm.group(1).upper()} {rm.group(3)}"
    start = rm.end()
    sub = text[start:pos]
    dm = re.search(r"def\s+(\w+)\s*\(", sub)
    handler = dm.group(1) if dm else "?"
    return route_str, handler


def _phase7_risk_hint(*, dep: str, route: str, handler: str) -> str:
    """Conservative hints for Phase 7 audit; not a substitute for code review."""
    blob = f"{handler} {route}".lower()
    if dep == "get_inventory_repo" and "/process" in route:
        return "HIGH — aisle processing; inventory entity drives provider/prompt resolution + job launch"
    if "/process" in route or "merge" in route or "export" in blob:
        return "typically HIGH — writes / side effects"
    if any(k in blob for k in ("cancel", "retry", "promote", "upload")):
        return "typically MEDIUM–HIGH — mutations"
    return "review manually (read paths may be SAFE)"


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
    files_with_hits: set[str] = set()
    for path in sorted(routes_dir.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        hits = list(pattern.finditer(text))
        if not hits:
            continue
        any_hits = True
        files_with_hits.add(path.name)
        print(f"\n{path.name}")
        for m in hits:
            param = m.group(1)
            dep = m.group(2)
            line_no = text[: m.start()].count("\n") + 1
            route, handler = _route_and_handler_before(text, m.start())
            hint = _phase7_risk_hint(dep=dep, route=route, handler=handler)
            print(f"  L{line_no}: {param} = Depends({dep})")
            if route:
                print(f"       route: {route}")
            if handler != "?":
                print(f"       handler: {handler}")
            print(f"       Phase 7 hint: {hint}")

    scanned = sorted(p.name for p in routes_dir.glob("*.py") if p.suffix == ".py")
    clean = [n for n in scanned if n not in files_with_hits and n != "__init__.py"]
    if clean:
        print("\n" + "-" * 72)
        print("Files with no Depends(get_*_repo) on route handlers:")
        for n in clean:
            print(f"  {n}")

    if not any_hits:
        print("\n(no Depends(get_*_repo) matches — v3 routes are clean at this layer.)")
    else:
        print("\nSuggested next refactors (when risk is acceptable)")
        print("- Replace each Depends(get_*_repo) with a dedicated query/command use case.")
        print("- Keep routes thin: parse/validate → use case → map errors → response.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
