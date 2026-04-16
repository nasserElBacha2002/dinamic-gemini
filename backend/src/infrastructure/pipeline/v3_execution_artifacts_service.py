"""
Durable worker artifact upload for v3 runs (Phase 2 split).

Keeps ``publish_worker_durable_artifacts`` and the "artifact store required" policy in one place
so :class:`~src.infrastructure.pipeline.v3_job_executor.V3JobExecutor` stays a coordinator.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

from src.infrastructure.pipeline.worker_durable_artifact_publisher import publish_worker_durable_artifacts
from src.infrastructure.storage.artifact_store import ArtifactStore

logger = logging.getLogger(__name__)


class V3ExecutionArtifactsService:
    """Uploads execution outputs (logs, reports) to the configured ArtifactStore."""

    def __init__(self, artifact_store: Optional[ArtifactStore]) -> None:
        self._artifact_store = artifact_store

    def require_store(self) -> None:
        """Raise with the same message the executor used when no store is configured."""
        if self._artifact_store is None:
            raise RuntimeError("Artifact store not configured; cannot upload durable worker outputs")

    def publish_worker_durables(
        self,
        *,
        job_id: str,
        run_segment: str,
        run_dir: Path,
    ) -> Dict[str, Dict[str, Any]]:
        """Publish durable artifacts; caller must have called :meth:`require_store` first."""
        assert self._artifact_store is not None
        return publish_worker_durable_artifacts(
            self._artifact_store,
            job_id=job_id,
            run_segment=run_segment,
            run_dir=run_dir,
        )
