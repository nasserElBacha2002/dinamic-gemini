"""Port: map ``hybrid_report`` JSON to v3 domain entities (injected from infrastructure)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from src.application.dto.mapped_aisle_result import MappedAisleResult


class HybridReportToDomainMapper(Protocol):
    def __call__(
        self,
        aisle_id: str,
        report: dict[str, Any],
        run_dir: Path,
        run_id: str,
        job_id: str,
        now: datetime,
        inventory_id: str,
        *,
        provider: str | None = None,
        model_name: str | None = None,
        prompt_composition: dict[str, Any] | None = None,
    ) -> MappedAisleResult: ...


__all__ = ["HybridReportToDomainMapper"]
