"""Phase 7 — compute available actions (job + snapshot + flags aware)."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingState,
    JobAssetProcessingStatus,
)
from src.domain.jobs.entities import Job


@dataclass(frozen=True)
class AvailableAssetActions:
    can_reprocess: bool = False
    can_retry_persistence: bool = False
    can_send_to_external: bool = False
    can_assign_manual: bool = False
    can_invalidate: bool = False
    can_view_sensitive_evidence: bool = False
    can_reconcile: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {
            "can_reprocess": self.can_reprocess,
            "can_retry_persistence": self.can_retry_persistence,
            "can_send_to_external": self.can_send_to_external,
            "can_assign_manual": self.can_assign_manual,
            "can_invalidate": self.can_invalidate,
            "can_view_sensitive_evidence": self.can_view_sensitive_evidence,
            "can_reconcile": self.can_reconcile,
        }


def _job_status_value(job: Job) -> str:
    status = getattr(job, "status", None)
    return str(getattr(status, "value", status) or "").upper()


def _snapshot_flags(job: Job) -> dict:
    params = job.engine_params_json if isinstance(job.engine_params_json, dict) else {}
    ident = params.get("identification_execution")
    return ident if isinstance(ident, dict) else {}


def compute_available_actions(
    *,
    job: Job,
    state: JobAssetProcessingState | None,
    has_manual_result: bool,
    has_reusable_external_normalized: bool,
    flags: dict[str, bool],
    view_sensitive: bool = False,
    historical_incomplete: bool = False,
    has_open_command: bool = False,
    executor_available: bool = True,
) -> AvailableAssetActions:
    obs = bool(flags.get("processing_observability_enabled"))
    reprocess_on = bool(flags.get("processing_asset_reprocess_enabled"))
    manual_on = bool(flags.get("processing_manual_actions_enabled"))
    # Prefer snapshot for historical identity; live flag only for current capability.
    snap = _snapshot_flags(job)
    snap_fallback = snap.get("external_fallback")
    if isinstance(snap_fallback, dict):
        fallback_on = bool(snap_fallback.get("enabled", False)) and bool(
            flags.get("external_fallback_per_image_enabled", False)
        )
    else:
        fallback_on = bool(flags.get("external_fallback_per_image_enabled", False))

    if not obs or state is None or historical_incomplete:
        return AvailableAssetActions(can_view_sensitive_evidence=view_sensitive)

    job_status = _job_status_value(job)
    cancelled_job = job_status in {"CANCELLED", "CANCELED"}
    processing = state.status is JobAssetProcessingStatus.PROCESSING
    cancelled = state.status is JobAssetProcessingStatus.CANCELLED or cancelled_job
    busy = processing or has_open_command

    can_reprocess = (
        reprocess_on
        and executor_available
        and not busy
        and not cancelled
        and state.status
        in (
            JobAssetProcessingStatus.RESOLVED,
            JobAssetProcessingStatus.UNRECOGNIZED,
            JobAssetProcessingStatus.PENDING_MANUAL_REVIEW,
            JobAssetProcessingStatus.PENDING,
            JobAssetProcessingStatus.FAILED_TECHNICAL,
        )
    )
    can_retry_persistence = (
        reprocess_on
        and executor_available
        and has_reusable_external_normalized
        and not busy
        and not cancelled
    )
    can_send_to_external = (
        fallback_on
        and reprocess_on
        and executor_available
        and not busy
        and not cancelled
        and state.status
        in (
            JobAssetProcessingStatus.UNRECOGNIZED,
            JobAssetProcessingStatus.PENDING_MANUAL_REVIEW,
            JobAssetProcessingStatus.FAILED_TECHNICAL,
            JobAssetProcessingStatus.PENDING,
        )
    )
    can_assign_manual = (
        manual_on and not busy and not cancelled and not has_manual_result
    )
    can_invalidate = (
        manual_on
        and not busy
        and not cancelled
        and (
            state.status is JobAssetProcessingStatus.RESOLVED
            or has_manual_result
            or bool(state.active_result_id)
        )
    )
    can_reconcile = (
        reprocess_on
        and executor_available
        and not busy
        and not cancelled
        and (
            has_reusable_external_normalized
            or bool(state.active_result_id)
        )
    )
    return AvailableAssetActions(
        can_reprocess=can_reprocess,
        can_retry_persistence=can_retry_persistence,
        can_send_to_external=can_send_to_external,
        can_assign_manual=can_assign_manual,
        can_invalidate=can_invalidate,
        can_view_sensitive_evidence=view_sensitive,
        can_reconcile=can_reconcile,
    )


__all__ = ["AvailableAssetActions", "compute_available_actions"]
