"""Default persist dependencies for V3JobExecutor unit tests."""

from __future__ import annotations

from typing import Any

from src.application.services.default_job_scoped_recompute_factory import (
    DefaultJobScopedRecomputeFactory,
)
from src.infrastructure.persistence.memory_artifact_manifest_store import (
    MemoryArtifactManifestStore,
)
from src.infrastructure.persistence.memory_finalization_stage_store import (
    MemoryFinalizationStageStore,
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
    stage_store = overrides.pop("finalization_stage_store", None) or MemoryFinalizationStageStore()
    manifest_store = overrides.pop("artifact_manifest_store", None) or MemoryArtifactManifestStore()
    uow_factory = overrides.pop(
        "job_result_uow_factory",
        MemoryJobResultUnitOfWorkFactory(stage_store=stage_store),
    )
    defaults: dict[str, Any] = {
        "raw_label_repo": MemoryRawLabelRepository(),
        "normalized_label_repo": MemoryNormalizedLabelRepository(),
        "final_count_repo": MemoryFinalCountRepository(),
        "job_scoped_recompute_factory": DefaultJobScopedRecomputeFactory(),
        "job_result_uow_factory": uow_factory,
        "finalization_stage_store": stage_store,
        "artifact_manifest_store": manifest_store,
    }
    defaults.update(overrides)
    return defaults
