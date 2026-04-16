"""Stage 8 — SQL Server persistence exports for **legacy** ``jobs`` / ``pallet_results`` / ``job_events``.

v3 operational persistence uses ``inventory_jobs`` and ``src/infrastructure/repositories/sql_*.py``.
For observability on legacy SQL access, see logger ``dinamic.legacy_sql`` and ``src/legacy/persistence_observability.py``.
"""

from src.database.repository import (
    JobEventsRepository,
    JobsRepository,
    PalletResultsRepository,
)
from src.database.sqlserver import SqlServerClient

__all__ = [
    "SqlServerClient",
    "JobsRepository",
    "PalletResultsRepository",
    "JobEventsRepository",
]
