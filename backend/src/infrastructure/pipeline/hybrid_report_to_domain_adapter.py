"""Wires :func:`map_hybrid_report_to_domain` as :class:`HybridReportToDomainMapper` for DI."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from src.application.dto.mapped_aisle_result import MappedAisleResult
from src.infrastructure.pipeline.v3_report_mapper import map_hybrid_report_to_domain


def default_map_hybrid_report_to_domain(
    aisle_id: str,
    report: dict[str, Any],
    run_dir: Path,
    run_id: str,
    job_id: str,
    now: datetime,
    inventory_id: str,
) -> MappedAisleResult:
    return map_hybrid_report_to_domain(
        aisle_id=aisle_id,
        report=report,
        run_dir=run_dir,
        run_id=run_id,
        job_id=job_id,
        now=now,
        inventory_id=inventory_id,
    )
