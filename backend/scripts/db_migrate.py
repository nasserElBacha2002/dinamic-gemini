"""Thin wrapper — schedules ``backend/`` on ``sys.path`` then runs package CLI.

Recommended (CI / local):
  cd backend && pip install -e .
  python scripts/db_migrate.py config-check   # preflight before apply/validate
  python scripts/db_migrate.py status | validate | apply

Equivalent module invocation (from ``backend/``, or with ``src`` on PYTHONPATH):
  cd backend && python -m src.database.migrations config-check
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from src.database.migrations.cli import main

if __name__ == "__main__":
    sys.exit(main())
