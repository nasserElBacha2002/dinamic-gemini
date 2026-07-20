"""Phase 7 — compute available actions for an asset (backend source of truth)."""

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

    def to_dict(self) -> dict[str, bool]:
        return {
            "can_reprocess": self.can_reprocess,
            "can_retry_persistence": self.can_retry_persistence,
            "can_send_to_external": self.can_send_to_external,
            "can_assign_manual": self.can_assign_manual,
            "can_invalidate": self.can_invalidate,
            "can_view_sensitive_evidence": self.can_view_sensitive_evidence,
        }


def compute_available_actions(
    *,
    job: Job,
    state: JobAssetProcessingState | None,
    has_manual_result: bool,
    has_reusable_external_normalized: bool,
    flags: dict[str, bool],
    view_sensitive: bool = False,
) -> AvailableAssetActions:
    del job  # reserved for future job-status gating
    obs = bool(flags.get("processing_observability_enabled"))
    reprocess_on = bool(flags.get("processing_asset_reprocess_enabled"))
    manual_on = bool(flags.get("processing_manual_actions_enabled"))
    fallback_on = bool(flags.get("external_fallback_per_image_enabled"))

    if not obs or state is None:
        return AvailableAssetActions(can_view_sensitive_evidence=view_sensitive)

    processing = state.status is JobAssetProcessingStatus.PROCESSING
    cancelled = state.status is JobAssetProcessingStatus.CANCELLED

    can_reprocess = (
        reprocess_on
        and not processing
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
        reprocess_on and has_reusable_external_normalized and not processing
    )
    can_send_to_external = (
        fallback_on
        and reprocess_on
        and not processing
        and state.status
        in (
            JobAssetProcessingStatus.UNRECOGNIZED,
            JobAssetProcessingStatus.PENDING_MANUAL_REVIEW,
            JobAssetProcessingStatus.FAILED_TECHNICAL,
        )
    )
    can_assign_manual = not processing and not cancelled
    can_invalidate = (
        manual_on
        and not processing
        and (
            state.status is JobAssetProcessingStatus.RESOLVED
            or has_manual_result
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
    )


__all__ = ["AvailableAssetActions", "compute_available_actions"]
