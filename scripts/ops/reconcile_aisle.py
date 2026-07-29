"""Deprecated alias for ``scripts.ops.inspect_aisle`` (Phase 7).

Sunset: **2026-12-31**. After that date this module may be removed.

Prefer::

  python -m scripts.ops.inspect_aisle --aisle-id <id> --dry-run --actor ops --reason 'check'

Kept so existing runbooks that invoke ``reconcile_aisle`` still work as inspect-only.

Deprecation is emitted on **stderr** (visible) — not a hidden warnings-module path.
"""

from __future__ import annotations

import sys
from pathlib import Path

_DEPRECATION_MSG = (
    "DEPRECATED: scripts.ops.reconcile_aisle — use scripts.ops.inspect_aisle instead "
    "(sunset 2026-12-31; ticket PHASE7-CLEANUP-RECONCILE-AISLE)."
)


def _emit_deprecation() -> None:
    print(_DEPRECATION_MSG, file=sys.stderr)


_emit_deprecation()

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.ops.inspect_aisle import main

if __name__ == "__main__":
    raise SystemExit(main())
