"""Deprecated alias — use scripts.ops.inspect_aisle.

Kept so existing runbooks that invoke reconcile_aisle still work as inspect-only.
"""

from __future__ import annotations

from scripts.ops.inspect_aisle import main

if __name__ == "__main__":
    raise SystemExit(main())
