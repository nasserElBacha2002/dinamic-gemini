"""
Legacy and parallel-persistence boundary (Stage 1 cleanup).

This package does **not** replace existing import paths yet. It exists to:
- centralize observability helpers for pre-v3 SQL surfaces
- document which modules are **not** part of the v3 operational persistence model

**v3 operational persistence (canonical for inventories / aisles / runs / reviews)** lives under
``src/infrastructure/repositories/sql_*.py`` and uses tables such as ``inventory_jobs``,
``positions``, ``review_actions``, etc.

**Legacy Stage-8 SQL persistence** (jobs / pallet_results / job_events) remains in
``src/database/repository.py`` and is still reachable from ``src/jobs/job_store.py`` and tests.
New product code should not add dependencies on that path without an explicit decision.
"""

from __future__ import annotations

__all__: list[str] = []
