"""Server reprocess domain types (Phase 7) — proposals never overwrite current authority."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ServerReprocessRunType(str, Enum):
    INITIAL_SERVER_PROCESSING = "INITIAL_SERVER_PROCESSING"
    SERVER_REPROCESS = "SERVER_REPROCESS"
    LOCAL_AUTHORITY_APPLY = "LOCAL_AUTHORITY_APPLY"


class ServerReprocessScopeType(str, Enum):
    FULL_AISLE = "FULL_AISLE"
    SELECTED_ASSETS = "SELECTED_ASSETS"
    FAILED_ONLY = "FAILED_ONLY"
    UNRECOGNIZED_ONLY = "UNRECOGNIZED_ONLY"
    PENDING_REVIEW_ONLY = "PENDING_REVIEW_ONLY"


class ServerReprocessRunStatus(str, Enum):
    REQUESTED = "REQUESTED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    TIMED_OUT = "TIMED_OUT"
    PARTIAL = "PARTIAL"


class ServerReprocessReviewStatus(str, Enum):
    NOT_REVIEWED = "NOT_REVIEWED"
    REVIEW_IN_PROGRESS = "REVIEW_IN_PROGRESS"
    REVIEW_COMPLETED = "REVIEW_COMPLETED"
    DISCARDED = "DISCARDED"
    ADOPTED_PARTIALLY = "ADOPTED_PARTIALLY"
    ADOPTED_COMPLETELY = "ADOPTED_COMPLETELY"


class ServerReprocessProcessingMode(str, Enum):
    CODE_SCAN = "CODE_SCAN"
    INTERNAL_OCR = "INTERNAL_OCR"
    GLOBAL_FALLBACK = "GLOBAL_FALLBACK"
    AUTO_PIPELINE = "AUTO_PIPELINE"


class ServerReprocessDifferenceType(str, Enum):
    SAME_RESULT = "SAME_RESULT"
    CODE_CHANGED = "CODE_CHANGED"
    QUANTITY_CHANGED = "QUANTITY_CHANGED"
    CODE_AND_QUANTITY_CHANGED = "CODE_AND_QUANTITY_CHANGED"
    PREVIOUS_UNRESOLVED_REMOTE_RESOLVED = "PREVIOUS_UNRESOLVED_REMOTE_RESOLVED"
    PREVIOUS_RESOLVED_REMOTE_UNRESOLVED = "PREVIOUS_RESOLVED_REMOTE_UNRESOLVED"
    REMOTE_AMBIGUOUS = "REMOTE_AMBIGUOUS"
    NO_PREVIOUS_RESULT = "NO_PREVIOUS_RESULT"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    NOT_COMPARABLE_GLOBAL_BATCH = "NOT_COMPARABLE_GLOBAL_BATCH"


class ServerReprocessProposalStatus(str, Enum):
    PROPOSED = "PROPOSED"
    ADOPTED = "ADOPTED"
    KEPT_CURRENT = "KEPT_CURRENT"
    DEFERRED = "DEFERRED"
    DISCARDED = "DISCARDED"
    STALE = "STALE"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class ServerReprocessAdoptionAction(str, Enum):
    ADOPT = "ADOPT"
    KEEP_CURRENT = "KEEP_CURRENT"
    EDIT_AND_ADOPT = "EDIT_AND_ADOPT"
    DEFER = "DEFER"


@dataclass(frozen=True)
class ServerReprocessRun:
    id: str
    request_id: str
    inventory_id: str
    aisle_id: str
    source_session_id: str | None
    company_id: str | None
    run_type: str
    strategy: str | None
    scope_type: str
    scope_json: dict[str, Any]
    snapshot_json: dict[str, Any]
    processing_mode: str
    reason: str
    status: str
    review_status: str
    requested_by: str
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    canceled_at: datetime | None
    failed_at: datetime | None
    failure_code: str | None
    failure_message: str | None
    pipeline_version: str | None
    model_version: str | None
    prompt_version: str | None
    supplier_profile_id: str | None
    linked_job_id: str | None
    has_prior_authority: bool
    row_version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ServerReprocessRunAsset:
    id: str
    run_id: str
    asset_id: str
    asset_hash: str | None
    previous_result_id: str | None
    previous_position_id: str | None
    previous_internal_code: str | None
    previous_quantity: float | None
    previous_resolved: bool
    created_at: datetime


@dataclass(frozen=True)
class ServerReprocessProposal:
    id: str
    run_id: str
    asset_id: str
    remote_result_id: str | None
    previous_result_id: str | None
    previous_position_id: str | None
    status: str
    difference_type: str
    internal_code: str | None
    quantity: float | None
    confidence: float | None
    source: str | None
    pipeline_version: str | None
    remote_resolved: bool
    review_status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ServerReprocessAdoption:
    id: str
    adoption_id: str
    run_id: str
    inventory_id: str
    aisle_id: str
    status: str
    adopted_by: str
    adopted_at: datetime
    item_count: int
    adopted_count: int
    kept_count: int
    deferred_count: int
    row_version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ServerReprocessAdoptionItem:
    id: str
    adoption_row_id: str
    proposal_id: str
    asset_id: str
    action: str
    expected_previous_result_id: str | None
    new_result_id: str | None
    new_position_id: str | None
    edit_internal_code: str | None
    edit_quantity: float | None
    created_at: datetime


@dataclass(frozen=True)
class RemoteProposalInput:
    """Remote processing output for one asset — never written as current authority."""

    asset_id: str
    remote_result_id: str | None = None
    internal_code: str | None = None
    quantity: float | None = None
    confidence: float | None = None
    source: str | None = None
    pipeline_version: str | None = None
    resolved: bool = False
    ambiguous: bool = False
    comparable: bool = True
    global_batch_unmapped: bool = False
    extra: dict[str, Any] = field(default_factory=dict)
