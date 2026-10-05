"""CLI wrapper for the read-only Offline Aisle package validator."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from src.application.services.offline_aisle_package_validator import (  # noqa: E402
    validate_offline_aisle_package_bytes,
)


def main() -> int:
    if len(sys.argv) != 2:
        print(
            json.dumps(
                {"valid": False, "errors": ["usage: validate_offline_aisle_package.py FILE"]}
            )
        )
        return 2

    package_path = Path(sys.argv[1])
    try:
        result = validate_offline_aisle_package_bytes(package_path.read_bytes())
    except OSError as exc:
        print(json.dumps({"valid": False, "errors": [f"read_error:{exc}"]}))
        return 2

    print(
        json.dumps(
            {
                "valid": result.ok,
                "errors": list(result.errors),
                "manifest": result.manifest,
            },
            separators=(",", ":"),
        )
    )
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
