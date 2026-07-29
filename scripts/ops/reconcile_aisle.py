"""Deprecated alias for ``scripts.ops.inspect_aisle`` (Phase 7).

Sunset: **2026-12-31**. After that date this module may be removed.

Prefer::

  python -m scripts.ops.inspect_aisle --aisle-id <id> --dry-run --actor ops --reason 'check'

Kept so existing runbooks that invoke ``reconcile_aisle`` still work as inspect-only.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "scripts.ops.reconcile_aisle is deprecated; use scripts.ops.inspect_aisle "
    "(sunset 2026-12-31)",
    DeprecationWarning,
    stacklevel=1,
)

from scripts.ops.inspect_aisle import main

if __name__ == "__main__":
    raise SystemExit(main())
