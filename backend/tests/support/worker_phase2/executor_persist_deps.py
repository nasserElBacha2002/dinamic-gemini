"""Default persist dependencies for V3JobExecutor unit tests."""

from __future__ import annotations

from typing import Any

from src.application.services.default_job_scoped_recompute_factory import (
    DefaultJobScopedRecomputeFactory,
)
from src.infrastructure.persistence.memory_job_result_unit_of_work import (
    MemoryJobResultUnitOfWorkFactory,
)
from src.infrastructure.repositories.memory_final_count_repository import MemoryFinalCountRepository
from src.infrastructure.repositories.memory_normalized_label_repository import (
    MemoryNormalizedLabelRepository,
)
from src.infrastructure.repositories.memory_raw_label_repository import MemoryRawLabelRepository


def memory_executor_persist_kwargs(**overrides: Any) -> dict[str, Any]:
    """Explicit memory-backed persist wiring required by V3JobExecutor."""
    defaults: dict[str, Any] = {
        "raw_label_repo": MemoryRawLabelRepository(),
        "normalized_label_repo": MemoryNormalizedLabelRepository(),
        "final_count_repo": MemoryFinalCountRepository(),
        "job_scoped_recompute_factory": DefaultJobScopedRecomputeFactory(),
        "job_result_uow_factory": MemoryJobResultUnitOfWorkFactory(),
    }
    defaults.update(overrides)
    return defaults
