"""Phase 7 aisle positioning operational read model (UX authority)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class PositioningReprocessMode(str, Enum):
    """Reprocess modes the backend actually supports."""

    REPROCESS_FULL_AISLE = "REPROCESS_FULL_AISLE"
    RECONCILE_ONLY = "RECONCILE_ONLY"


class ManualOverridePolicy(str, Enum):
    """Honest continuity contract for manual overrides across reprocess modes."""

    PRESERVED = "PRESERVED"
    REQUIRES_REVIEW_AFTER_NEW_JOB = "REQUIRES_REVIEW_AFTER_NEW_JOB"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class PositioningWarningSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class PositioningAllowedActions:
    process: bool = False
    reprocess: bool = False
    recover: bool = False
    review: bool = False
    correct_position: bool = False
    restore_automatic: bool = False
    reconcile_only: bool = False

    def as_dict(self) -> dict[str, bool]:
        return {
            "process": self.process,
            "reprocess": self.reprocess,
            "recover": self.recover,
            "review": self.review,
            "correct_position": self.correct_position,
            "restore_automatic": self.restore_automatic,
            "reconcile_only": self.reconcile_only,
        }


@dataclass(frozen=True)
class PositioningOperationalWarning:
    code: str
    title: str
    description: str
    severity: PositioningWarningSeverity
    affected_count: int = 0
    allowed_actions: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "title": self.title,
            "description": self.description,
            "severity": self.severity.value,
            "affected_count": self.affected_count,
            "allowed_actions": list(self.allowed_actions),
        }


@dataclass(frozen=True)
class UnassignedCauseBucket:
    cause: str
    count: int
    suggested_action: str


@dataclass(frozen=True)
class AisleOperationalPositioningView:
    """Authoritative aisle positioning UX summary — do not recompute in clients."""

    inventory_id: str
    aisle_id: str
    client_id: str | None
    processing_state: str
    active_job_id: str | None
    result_job_id: str | None
    reconciliation_status: str | None
    reconciliation_id: str | None
    reconciliation_version: str | None
    total_results: int
    assigned_results: int
    unassigned_results: int
    assigned_automatic: int
    assigned_manual: int
    unassigned_automatic: int
    unassigned_manual: int
    manual_overrides_count: int
    invalid_positions_count: int
    stale_results_count: int
    unordered_assets_count: int
    ambiguous_detections_count: int
    detections_count: int
    recoverable: bool
    can_process: bool
    can_reprocess: bool
    can_recover: bool
    can_review: bool
    can_correct: bool
    allowed_actions: PositioningAllowedActions
    warnings: tuple[PositioningOperationalWarning, ...] = ()
    unassigned_by_cause: tuple[UnassignedCauseBucket, ...] = ()
    supported_reprocess_modes: tuple[str, ...] = ()
    last_updated_at: datetime | None = None
    feature_flags: dict[str, bool] = field(default_factory=dict)
    has_dinamic_scanner_txt_import: bool = False


@dataclass(frozen=True)
class PositioningSequenceFrame:
    sequence_number: int | None
    source_asset_id: str
    filename: str | None
    position_detection_status: str | None
    position_label_name: str | None
    transition_action: str | None
    transition_message: str | None
    product_count: int
    automatic_assignment_summaries: tuple[str, ...] = ()
    effective_assignment_summaries: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    #: Classification reason (additive; optional for older clients).
    reason_code: str | None = None
    position_label_id: str | None = None
