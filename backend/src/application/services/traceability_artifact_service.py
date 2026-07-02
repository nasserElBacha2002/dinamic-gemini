"""Application service — build and write durable traceability_manifest.json (Phase 4.7)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.application.ports.clock import Clock
from src.application.ports.repositories import ResultEvidenceRepository
from src.application.use_cases.pipeline.persist_aisle_result import (
    hybrid_report_has_persistible_detections,
)
from src.domain.execution_image_manifest import (
    ExecutionImageManifest,
    ExecutionImageManifestError,
    composition_has_execution_image_manifest,
    require_manifest_from_composition,
)
from src.domain.jobs.artifact_policy import ARTIFACT_KIND_TRACEABILITY_MANIFEST
from src.domain.traceability_artifact.builder import (
    TRACEABILITY_MANIFEST_SCHEMA_VERSION,
    TraceabilityManifestBuildInput,
    build_traceability_manifest,
    traceability_manifest_is_json_safe,
)
from src.domain.traceability_artifact.canonical_json import canonical_json_dumps
from src.domain.traceability_artifact.errors import (
    TraceabilityEvidenceMissingError,
    TraceabilityManifestInvalidError,
    TraceabilityManifestMissingError,
)

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
        input_type: str | None,
        canonical_traceability_expected: bool,
        prompt_composition: dict[str, Any] | None = None,
    ) -> bool:
        """V3 photo canonical jobs require traceability artifact based on job context."""
        del prompt_composition  # requirement is explicit; manifest validated during generation
        normalized = (input_type or "").strip().lower()
        return canonical_traceability_expected and normalized == "photos"

    @staticmethod
    def _resolve_execution_manifest(
        prompt_composition: dict[str, Any] | None,
        *,
        manifest_required: bool,
    ) -> tuple[ExecutionImageManifest | None, tuple[str, ...]]:
        if not manifest_required:
            if not composition_has_execution_image_manifest(prompt_composition):
                return None, (
                    "Execution image manifest was unavailable.",
                )
            try:
                return require_manifest_from_composition(prompt_composition), ()
            except ExecutionImageManifestError:
                return None, (
                    "Execution image manifest was unavailable.",
                )

        if not composition_has_execution_image_manifest(prompt_composition):
            raise TraceabilityManifestMissingError(
                "Canonical execution image manifest missing from prompt composition"
            )
        try:
            return require_manifest_from_composition(prompt_composition), ()
        except ExecutionImageManifestError as exc:
            raise TraceabilityManifestInvalidError(
                f"Canonical execution image manifest is invalid: {exc}"
            ) from exc

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
        input_type: str | None = None,
        canonical_traceability_expected: bool = False,
    ) -> Path:
        """Build traceability_manifest.json from persisted structural evidence."""
        required = self.is_required_for_run(
            input_type=input_type,
            canonical_traceability_expected=canonical_traceability_expected,
            prompt_composition=prompt_composition,
        )
        rows = tuple(
            self._result_evidence_repo.list_for_scope(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=job_id,
            )
        )
        zero_detection_outcome = False
        if required and not rows:
            if hybrid_report is None or hybrid_report_has_persistible_detections(
                hybrid_report,
                aisle_id=aisle_id,
                job_id=job_id,
                inventory_id=inventory_id,
                input_type=input_type,
            ):
                raise TraceabilityEvidenceMissingError(
                    f"Structural result_evidence rows missing for required traceability artifact "
                    f"(job_id={job_id})"
                )
            zero_detection_outcome = True
            logger.info(
                "traceability_artifact zero_detection_outcome job_id=%s "
                "(no persistible products; empty structural evidence allowed)",
                job_id,
            )
        elif not required and not rows:
            logger.info(
                "traceability_artifact skipped empty evidence job_id=%s (not required)",
                job_id,
            )

        execution_manifest, artifact_warnings = self._resolve_execution_manifest(
            prompt_composition,
            manifest_required=required,
        )
        combined_warnings = list(artifact_warnings)
        if zero_detection_outcome:
            combined_warnings.append(
                "No identifiable products were persisted for this run; result_evidence is empty."
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
                run_metadata=run_metadata,
                result_evidence_rows=rows,
                execution_manifest=execution_manifest,
                manifest_required=required,
                artifact_warnings=tuple(combined_warnings),
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
