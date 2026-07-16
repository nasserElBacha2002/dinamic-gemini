"""Job Observability HTTP routes (extracted from aisle operations).

Public URLs remain under ``/api/v3/inventories/{inventory_id}/aisles/...``.
Handlers that mutate aisle lifecycle (create/process/merge/export) stay in
``aisles.py``. Observability read/download surfaces live here.
"""

from __future__ import annotations

# Re-export the shared aisles router Observability endpoints by attaching
# them onto this module's router while preserving exact URL paths.
#
# Physical move strategy (safe): Observability handlers remain registered on
# the inventories/aisles ``router`` object defined in ``aisles.py`` so existing
# include_router wiring and tests keep working. This module documents the
# Observability surface and re-exports the capability/sanitization helpers used
# by those handlers for a stable import path.
from src.application.services.observability_access import (  # noqa: F401
    CAP_DOWNLOAD_ARTIFACTS,
    CAP_VIEW_ARTIFACT_PREVIEW,
    CAP_VIEW_FULL_PROMPT,
    CAP_VIEW_STACK_TRACES,
    CAP_VIEW_SUMMARY,
    CAP_VIEW_TECHNICAL_LOGS,
)
from src.application.services.observability_output_sanitizer import (  # noqa: F401
    sanitize_execution_log_events,
    sanitize_observability_value,
)

OBSERVABILITY_ROUTE_SUFFIXES = (
    "/jobs/{job_id}/artifacts",
    "/jobs/{job_id}/artifacts/{artifact_id}",
    "/jobs/{job_id}/artifacts/{artifact_id}/download",
    "/jobs/{job_id}/artifacts/{artifact_id}/preview",
    "/jobs/{job_id}/retry-chain",
    "/jobs/{job_id}/execution-log",
    "/jobs/{job_id}/execution-log.txt",
    "/jobs/{job_id}/execution-log/page",
    "/jobs/{job_id}/timeline",
    "/jobs/{job_id}/errors",
    "/jobs/{job_id}/hybrid-report",
    "/jobs/{job_id}/auditability",
    "/jobs/{job_id}/traceability",
)
