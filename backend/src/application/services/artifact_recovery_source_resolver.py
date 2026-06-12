"""Resolve local artifact sources for manual republication — Phase 3.4."""

from __future__ import annotations

from pathlib import Path

from src.application.services.job_artifact_verifier import JobArtifactVerifier
from src.domain.jobs.artifact_policy import (
    ARTIFACT_KIND_EXECUTION_LOG,
    ARTIFACT_KIND_HYBRID_REPORT_CSV,
    ARTIFACT_KIND_HYBRID_REPORT_JSON,
    REQUIRED_ARTIFACT_KINDS,
)
from src.domain.jobs.entities import Job
from src.domain.jobs.finalization_recovery import (
    ArtifactRecoverySource,
    ArtifactRecoverySourceStatus,
)
from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
    DEFAULT_V3_WORKER_RUN_SEGMENT,
)

_KIND_TO_FILENAME = {
    ARTIFACT_KIND_EXECUTION_LOG: "execution_log.jsonl",
    ARTIFACT_KIND_HYBRID_REPORT_JSON: "hybrid_report.json",
    ARTIFACT_KIND_HYBRID_REPORT_CSV: "hybrid_report.csv",
}


class ArtifactRecoverySourceResolver:
    """Determine whether artifact bytes can be recovered without provider re-execution."""

    def __init__(
        self,
        *,
        artifact_verifier: JobArtifactVerifier,
        output_dir: Path | str,
    ) -> None:
        self._artifact_verifier = artifact_verifier
        self._output_dir = Path(output_dir)

    def resolve_all(self, job: Job) -> list[ArtifactRecoverySource]:
        return [self.resolve_kind(job, kind) for kind in sorted(REQUIRED_ARTIFACT_KINDS)]

    def resolve_kind(self, job: Job, artifact_kind: str) -> ArtifactRecoverySource:
        verification = self._artifact_verifier.verify_entry(job.id, artifact_kind)
        if verification.verdict.value == "confirmed":
            return ArtifactRecoverySource(
                artifact_kind=artifact_kind,
                status=ArtifactRecoverySourceStatus.AVAILABLE_EXACT,
                detail="already_verified_in_storage",
            )

        run_dir = self._resolve_run_dir(job)
        if run_dir is None:
            return ArtifactRecoverySource(
                artifact_kind=artifact_kind,
                status=ArtifactRecoverySourceStatus.NOT_AVAILABLE,
                detail="run_dir_not_resolved",
            )

        filename = _KIND_TO_FILENAME.get(artifact_kind)
        if filename is None:
            return ArtifactRecoverySource(
                artifact_kind=artifact_kind,
                status=ArtifactRecoverySourceStatus.NOT_AVAILABLE,
                detail="unknown_artifact_kind",
            )

        local_path = run_dir / filename
        if local_path.is_file():
            return ArtifactRecoverySource(
                artifact_kind=artifact_kind,
                status=ArtifactRecoverySourceStatus.AVAILABLE_EXACT,
                run_dir=str(run_dir),
                local_path=str(local_path),
            )

        if artifact_kind == ARTIFACT_KIND_HYBRID_REPORT_JSON:
            reconstructed = self._reconstruct_json_from_result(job, run_dir)
            if reconstructed is not None:
                return ArtifactRecoverySource(
                    artifact_kind=artifact_kind,
                    status=ArtifactRecoverySourceStatus.AVAILABLE_RECONSTRUCTED,
                    run_dir=str(run_dir),
                    local_path=str(reconstructed),
                    detail="reconstructed_from_result_json_report_path",
                )

        if artifact_kind == ARTIFACT_KIND_EXECUTION_LOG:
            return ArtifactRecoverySource(
                artifact_kind=artifact_kind,
                status=ArtifactRecoverySourceStatus.NOT_AVAILABLE,
                detail="execution_log_not_reconstructable_from_domain",
            )

        if artifact_kind == ARTIFACT_KIND_HYBRID_REPORT_CSV:
            return ArtifactRecoverySource(
                artifact_kind=artifact_kind,
                status=ArtifactRecoverySourceStatus.NOT_AVAILABLE,
                detail="optional_csv_absent",
            )

        return ArtifactRecoverySource(
            artifact_kind=artifact_kind,
            status=ArtifactRecoverySourceStatus.AMBIGUOUS,
            run_dir=str(run_dir),
            detail="source_ambiguous",
        )

    def _resolve_run_dir(self, job: Job) -> Path | None:
        result = job.result_json or {}
        report_path = result.get("report_path")
        if isinstance(report_path, str) and report_path.strip():
            parent = Path(report_path).parent
            if parent.is_dir():
                return parent
        candidate = self._output_dir / job.id / DEFAULT_V3_WORKER_RUN_SEGMENT
        if candidate.is_dir():
            return candidate
        legacy = self._output_dir / job.id / "run"
        if legacy.is_dir():
            return legacy
        return None

    def _reconstruct_json_from_result(self, job: Job, run_dir: Path) -> Path | None:
        result = job.result_json or {}
        report_path = result.get("report_path")
        if isinstance(report_path, str) and report_path.strip():
            path = Path(report_path)
            if path.is_file():
                target = run_dir / "hybrid_report.json"
                if not target.exists():
                    return path
                if path.resolve() == target.resolve():
                    return target
                return path
        return None
