#!/usr/bin/env python3
"""Patch docker-compose.yml host-side port for service bindings to container port 8000.

Used by deploy workflows to avoid host port conflicts (e.g. map 8001:8000 instead of 8000:8000).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PATCH_FAILED_MSG = (
    "ERROR: Could not find any host→container port mapping ending in :8000 in docker-compose.yml. "
    "Expected forms include \"8000:8000\", '8000:8000', - 8000:8000, or \"127.0.0.1:8000:8000\"."
)


def _already_patched_to_host_port(text: str, host_port: str) -> bool:
    """True if compose already exposes the requested host port to container 8000."""
    hp = re.escape(host_port)
    if re.search(rf'"{hp}:8000"', text):
        return True
    if re.search(rf"'{hp}:8000'", text):
        return True
    if re.search(rf"^(\s*-\s+){hp}:8000(\s*(?:#.*)?)$", text, re.MULTILINE):
        return True
    if re.search(rf'"[0-9.]+:{hp}:8000"', text):
        return True
    if re.search(rf"'[0-9.]+:{hp}:8000'", text):
        return True
    return False


def patch_compose_text(text: str, host_port: str) -> str:
    """Replace host port for any binding whose container port is 8000. Preserves quote style.

    Applies rules in order so three-part IP bindings are not partially matched by two-part rules.
    """
    if not host_port.strip():
        raise ValueError("host_port must be non-empty")
    host_port = host_port.strip()
    if not host_port.isdigit():
        # Allow numeric strings only (compose host ports are integers in our supported forms)
        raise ValueError(f"host_port must be a numeric string, got {host_port!r}")

    original = text
    t = text

    # 1) IP:hostPort:containerPort (quoted) — must run before two-part patterns
    t = re.sub(r'"([0-9.]+):(\d+):8000"', rf'"\1:{host_port}:8000"', t)
    t = re.sub(r"'([0-9.]+):(\d+):8000'", rf"'\1:{host_port}:8000'", t)

    # 2) hostPort:containerPort (quoted)
    t = re.sub(r'"(\d+):8000"', f'"{host_port}:8000"', t)
    t = re.sub(r"'(\d+):8000'", f"'{host_port}:8000'", t)

    # 3) Unquoted YAML list item: - 8000:8000  # optional comment
    t = re.sub(
        r"^(\s*-\s+)(\d+):8000(\s*(?:#.*)?)$",
        rf"\g<1>{host_port}:8000\3",
        t,
        flags=re.MULTILINE,
    )

    if t == original:
        if _already_patched_to_host_port(original, host_port):
            return original
        raise ValueError(PATCH_FAILED_MSG)
    return t


def _main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--compose", required=True, help="Path to docker-compose.yml")
    p.add_argument("--host-port", required=True, dest="host_port", help="Host port to bind (e.g. 8001)")
    args = p.parse_args(argv)

    compose_path = Path(args.compose)
    if not compose_path.is_file():
        print(f"ERROR: compose file not found: {compose_path}", file=sys.stderr)
        return 1

    text = compose_path.read_text(encoding="utf-8")
    try:
        new_text = patch_compose_text(text, args.host_port)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    compose_path.write_text(new_text, encoding="utf-8")
    print("Patched docker-compose.yml port mapping:")
    for line in new_text.splitlines():
        if ":8000" in line or args.host_port in line:
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
