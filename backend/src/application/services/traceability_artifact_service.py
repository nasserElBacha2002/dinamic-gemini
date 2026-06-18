"""Application service — build and write durable traceability_manifest.json (Phase 4.7)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.application.ports.clock import Clock
from src.application.ports.repositories import ResultEvidenceRepository
from src.domain.execution_image_manifest import composition_has_execution_image_manifest
from src.domain.jobs.artifact_policy import ARTIFACT_KIND_TRACEABILITY_MANIFEST
from src.domain.traceability_artifact.builder import (
    TRACEABILITY_MANIFEST_SCHEMA_VERSION,
    TraceabilityManifestBuildInput,
    build_traceability_manifest,
    traceability_manifest_is_json_safe,
)
from src.domain.traceability_artifact.errors import TraceabilityEvidenceMissingError
from src.domain.traceability_artifact.canonical_json import canonical_json_dumps

logger = logging.getLogger(__name__)

TRACEABILITY_MANIFEST_FILENAME = "traceability_manifest.json"


class TraceabilityArtifactService:
    """Orchestrates structural reads and deterministic artifact file generation."""

    def __init__(
        self,
        *,
        result_evidence_repo: ResultEvidenceRepository,
        clock: Clock,
    ) -> None:
        self._result_evidence_repo = result_evidence_repo
        self._clock = clock

    @staticmethod
    def is_required_for_run(
        *,
        prompt_composition: dict[str, Any] | None,
    ) -> bool:
        """V3 photo jobs with canonical execution image manifest require the artifact."""
        return composition_has_execution_image_manifest(prompt_composition)

    def generate_and_write(
        self,
        *,
        job_id: str,
        inventory_id: str,
        aisle_id: str,
        run_id: str,
        run_dir: Path,
        provider: str | None,
        model_name: str | None,
        prompt_composition: dict[str, Any] | None,
        run_metadata: dict[str, Any] | None,
        hybrid_report: dict[str, Any] | None = None,
    ) -> Path:
        """Build traceability_manifest.json from persisted structural evidence."""
        del hybrid_report  # structural rows are authoritative; hybrid_report not used when rows exist
        required = self.is_required_for_run(prompt_composition=prompt_composition)
        rows = tuple(
            self._result_evidence_repo.list_for_scope(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=job_id,
            )
        )
        if required and not rows:
            raise TraceabilityEvidenceMissingError(
                f"Structural result_evidence rows missing for required traceability artifact "
                f"(job_id={job_id})"
            )
        if not required and not rows:
            logger.info(
                "traceability_artifact skipped empty evidence job_id=%s (not required)",
                job_id,
            )

        manifest_body = build_traceability_manifest(
            TraceabilityManifestBuildInput(
                job_id=job_id,
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                run_id=run_id,
                provider=provider,
                model_name=model_name,
                created_at=self._clock.now(),
                prompt_composition=prompt_composition,
                run_metadata=run_metadata,
                result_evidence_rows=rows,
                manifest_required=True,
            )
        )
        if not traceability_manifest_is_json_safe(manifest_body):
            raise ValueError("traceability_manifest content is not JSON-safe")

        out_path = Path(run_dir) / TRACEABILITY_MANIFEST_FILENAME
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            canonical_json_dumps(manifest_body) + "\n",
            encoding="utf-8",
        )
        logger.info(
            "traceability_artifact written job_id=%s path=%s schema=%s rows=%d",
            job_id,
            out_path,
            TRACEABILITY_MANIFEST_SCHEMA_VERSION,
            len(rows),
        )
        return out_path

    @staticmethod
    def artifact_kind() -> str:
        return ARTIFACT_KIND_TRACEABILITY_MANIFEST
