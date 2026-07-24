"""Aisle revision domain types (Phase 8) — corrections without destructive history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AisleRevisionType(str, Enum):
    MANUAL_CORRECTION = "MANUAL_CORRECTION"
    SERVER_PROPOSAL_ADOPTION = "SERVER_PROPOSAL_ADOPTION"
    ROLLBACK = "ROLLBACK"
    EXCLUSION_CHANGE = "EXCLUSION_CHANGE"
    REOPEN_AND_EDIT = "REOPEN_AND_EDIT"


class AisleRevisionStatus(str, Enum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    READY_TO_APPLY = "READY_TO_APPLY"
    APPLYING = "APPLYING"
    COMPLETED = "COMPLETED"
    CANCELED = "CANCELED"
    FAILED = "FAILED"
    CONFLICTED = "CONFLICTED"


class AisleRevisionItemStatus(str, Enum):
    UNCHANGED = "UNCHANGED"
    MODIFIED = "MODIFIED"
    EXCLUDED = "EXCLUDED"
    RESTORED = "RESTORED"
    ADOPT_REMOTE = "ADOPT_REMOTE"
    ROLLED_BACK = "ROLLED_BACK"
    CONFLICTED = "CONFLICTED"


class AisleRevisionProposalSource(str, Enum):
    MANUAL = "MANUAL"
    SERVER_REPROCESS_PROPOSAL = "SERVER_REPROCESS_PROPOSAL"
    ROLLBACK_SOURCE = "ROLLBACK_SOURCE"
    EXCLUSION_CHANGE = "EXCLUSION_CHANGE"
    UNCHANGED = "UNCHANGED"


class AisleRevisionDiffKind(str, Enum):
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    CODE_CHANGED = "CODE_CHANGED"
    QUANTITY_CHANGED = "QUANTITY_CHANGED"
    EXCLUDED = "EXCLUDED"
    RESTORED = "RESTORED"
    UNCHANGED = "UNCHANGED"


_EDITABLE = frozenset(
    {
        AisleRevisionStatus.DRAFT.value,
        AisleRevisionStatus.OPEN.value,
        AisleRevisionStatus.IN_REVIEW.value,
        AisleRevisionStatus.READY_TO_APPLY.value,
    }
)

_OPEN_STATUSES = frozenset(
    {
        AisleRevisionStatus.DRAFT.value,
        AisleRevisionStatus.OPEN.value,
        AisleRevisionStatus.IN_REVIEW.value,
        AisleRevisionStatus.READY_TO_APPLY.value,
        AisleRevisionStatus.APPLYING.value,
    }
)


def revision_is_editable(status: str) -> bool:
    return (status or "").strip() in _EDITABLE


def revision_is_open(status: str) -> bool:
    return (status or "").strip() in _OPEN_STATUSES


@dataclass(frozen=True)
class AisleRevision:
    id: str
    inventory_id: str
    aisle_id: str
    base_finalization_id: str
    new_finalization_id: str | None
    revision_type: str
    status: str
    reason: str
    requested_by: str
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    canceled_at: datetime | None
    failed_at: datetime | None
    failure_code: str | None
    failure_message: str | None
    apply_id: str | None
    snapshot_json: str
    content_hash: str
    row_version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class AisleRevisionItem:
    id: str
    revision_id: str
    asset_id: str
    base_result_id: str | None
    base_position_id: str | None
    proposed_internal_code: str | None
    proposed_quantity: int | None
    proposed_exclusion_state: str | None
    proposal_source: str
    proposal_reference_id: str | None
    change_reason: str | None
    item_status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class PositionVersion:
    id: str
    position_id: str
    version: int
    aisle_id: str
    asset_id: str
    internal_code: str
    quantity: int | None
    result_id: str | None
    is_current: bool
    supersedes_position_version_id: str | None
    revision_id: str | None
    revision_item_id: str | None
    created_by: str
    created_at: datetime
    content_hash: str


@dataclass(frozen=True)
class AisleRevisionDiffEntry:
    asset_id: str
    kind: str
    base_internal_code: str | None
    proposed_internal_code: str | None
    base_quantity: int | None
    proposed_quantity: int | None
    item_status: str
    proposal_source: str
