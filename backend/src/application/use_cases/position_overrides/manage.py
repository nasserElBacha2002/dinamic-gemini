"""Create, change, remove, restore, and audit manual product-position overrides."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from src.application.dto.access_principal import AccessPrincipal
from src.application.ports.client_position_label_repository import ClientPositionLabelRepository
from src.application.ports.manual_position_override_repository import (
    ManualPositionOverrideRepository,
)
from src.application.ports.position_reconciliation_repository import (
    PositionReconciliationRepository,
)
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    JobRepository,
    PositionRepository,
    ProductRecordRepository,
)
from src.application.position_override_errors import (
    PositionOverrideConflictError,
    PositionOverrideCrossTenantError,
    PositionOverrideFeatureDisabledError,
    PositionOverrideIdempotencyConflictError,
    PositionOverrideInvalidActionError,
    PositionOverrideInvalidLabelError,
    PositionOverrideLabelInvalidatedError,
    PositionOverrideNotFoundError,
    PositionOverrideResultNotActiveError,
    PositionOverrideResultNotFoundError,
)
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.application.services.position_override_access import (
    CAP_AUDIT,
    CAP_CREATE,
    CAP_REMOVE,
    CAP_RESTORE,
    require_position_override_capability,
)
from src.application.services.position_overrides.effective_position_reader import (
    EffectivePositionReader,
)
from src.domain.client_position_label.entities import ClientPositionLabelStatus
from src.domain.position_overrides.entities import (
    EffectiveProductPositionView,
    ManualProductPositionOverride,
    PositionOverrideAction,
    PositionOverrideReasonCode,
)
from src.domain.position_reconciliation.entities import ProductPositionAssignment
from src.domain.positions.entities import PositionStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PositionOverrideCommand:
    inventory_id: str
    job_id: str
    result_id: str
    action: PositionOverrideAction
    position_label_id: str | None
    reason_code: PositionOverrideReasonCode
    reason_text: str | None
    expected_effective_version: int
    idempotency_key: str
    principal: AccessPrincipal


@dataclass(frozen=True)
class PositionOverrideMutationResult:
    revision: ManualProductPositionOverride
    effective: EffectiveProductPositionView


class ManagePositionOverrideUseCase:
    def __init__(
        self,
        *,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        position_repo: PositionRepository,
        product_repo: ProductRecordRepository,
        label_repo: ClientPositionLabelRepository,
        override_repo: ManualPositionOverrideRepository,
        effective_reader: EffectivePositionReader,
        access_policy: InventoryAccessPolicy,
        writes_enabled: bool,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._position_repo = position_repo
        self._product_repo = product_repo
        self._label_repo = label_repo
        self._override_repo = override_repo
        self._effective_reader = effective_reader
        self._access_policy = access_policy
        self._writes_enabled = writes_enabled

    def execute(self, command: PositionOverrideCommand) -> PositionOverrideMutationResult:
        capability = {
            PositionOverrideAction.REMOVE_POSITION: CAP_REMOVE,
            PositionOverrideAction.RESTORE_AUTOMATIC: CAP_RESTORE,
        }.get(command.action, CAP_CREATE)
        require_position_override_capability(command.principal, capability)
        if not self._writes_enabled:
            raise PositionOverrideFeatureDisabledError(
                "Manual position override writes are disabled."
            )
        inventory, aisle_id, source_asset_id = self._validate_scope(command)
        client_id = (inventory.client_id or "").strip()
        if not client_id:
            raise PositionOverrideCrossTenantError(
                "Inventory has no client scope."
            )
        reason_text = self._validated_reason(command.reason_code, command.reason_text)
        label_id, label_name = self._validated_label(command, client_id)

        replay = self._override_repo.get_by_idempotency_key(
            client_id, command.idempotency_key
        )
        if replay is not None:
            if (
                replay.job_id != command.job_id
                or replay.result_id != command.result_id
                or replay.override_action is not command.action
                or replay.new_position_label_id != label_id
                or replay.reason_code is not command.reason_code
                or replay.reason_text != reason_text
            ):
                raise PositionOverrideIdempotencyConflictError(
                    "Idempotency key was reused with a different payload."
                )
            effective = self._effective_reader.load_for_job(
                command.job_id, result_ids=[command.result_id]
            )[command.result_id]
            return PositionOverrideMutationResult(revision=replay, effective=effective)

        effective_before = self._effective_reader.load_for_job(
            command.job_id, result_ids=[command.result_id]
        )[command.result_id]
        if effective_before.version != command.expected_effective_version:
            logger.info(
                "event=position_override_conflict job_id=%s result_id=%s actor_user_id=%s",
                command.job_id,
                command.result_id,
                command.principal.actor_id,
            )
            raise PositionOverrideConflictError(
                "The effective position changed.",
                current_version=effective_before.version,
                current_effective_position=effective_before.effective_position,
            )

        active = self._override_repo.get_active(command.job_id, command.result_id)
        if (
            command.action is PositionOverrideAction.RESTORE_AUTOMATIC
            and active is None
        ):
            raise PositionOverrideNotFoundError(
                "No active manual position override exists."
            )
        now = datetime.now(timezone.utc)
        revision = ManualProductPositionOverride(
            id=str(uuid4()),
            client_id=client_id,
            inventory_id=command.inventory_id,
            aisle_id=aisle_id,
            job_id=command.job_id,
            result_id=command.result_id,
            source_asset_id=source_asset_id or effective_before.source_asset_id,
            automatic_assignment_id=None,
            automatic_reconciliation_id=effective_before.automatic_reconciliation_id,
            previous_effective_position_label_id=(
                effective_before.effective_position.id
                if effective_before.effective_position
                else None
            ),
            new_position_label_id=label_id,
            new_position_name_snapshot=label_name,
            override_action=command.action,
            reason_code=command.reason_code,
            reason_text=reason_text,
            created_by_user_id=command.principal.actor_id,
            created_by_role=next(iter(sorted(command.principal.roles)), "unknown"),
            idempotency_key=command.idempotency_key.strip(),
            version=effective_before.version + 1,
            is_active=command.action is not PositionOverrideAction.RESTORE_AUTOMATIC,
            superseded_override_id=active.id if active else None,
            created_at=now,
            updated_at=now,
            deactivated_at=(
                now if command.action is PositionOverrideAction.RESTORE_AUTOMATIC else None
            ),
        )
        saved = self._override_repo.insert_revision_atomically(
            revision,
            expected_active_version=active.version if active else 0,
        )
        effective = self._effective_reader.load_for_job(
            command.job_id, result_ids=[command.result_id]
        )[command.result_id]
        event = {
            PositionOverrideAction.ASSIGN_POSITION: "position_override_created",
            PositionOverrideAction.CHANGE_POSITION: "position_override_changed",
            PositionOverrideAction.REMOVE_POSITION: "position_override_removed",
            PositionOverrideAction.RESTORE_AUTOMATIC: "position_override_restored",
        }[command.action]
        logger.info(
            "event=%s client_id=%s inventory_id=%s aisle_id=%s job_id=%s "
            "result_id=%s override_id=%s action=%s reason_code=%s actor_user_id=%s",
            event,
            client_id,
            command.inventory_id,
            aisle_id,
            command.job_id,
            command.result_id,
            saved.id,
            command.action.value,
            command.reason_code.value,
            command.principal.actor_id,
        )
        return PositionOverrideMutationResult(revision=saved, effective=effective)

    def _validate_scope(self, command: PositionOverrideCommand):
        inventory = self._access_policy.require_inventory(
            command.inventory_id, command.principal
        )
        job = self._job_repo.get_by_id(command.job_id)
        product = self._product_repo.get_by_id(command.result_id)
        if product is None:
            raise PositionOverrideResultNotFoundError("Result not found.")
        position = self._position_repo.get_by_id(product.position_id)
        if position is None:
            raise PositionOverrideResultNotFoundError("Result not found.")
        aisle = self._aisle_repo.get_by_id(position.aisle_id)
        if (
            job is None
            or aisle is None
            or aisle.inventory_id != command.inventory_id
            or job.target_id != aisle.id
            or position.job_id != command.job_id
        ):
            raise PositionOverrideResultNotFoundError("Result not found in job scope.")
        if position.status is PositionStatus.DELETED:
            raise PositionOverrideResultNotActiveError("Result is not active.")
        return inventory, aisle.id, None

    def _validated_label(
        self, command: PositionOverrideCommand, client_id: str
    ) -> tuple[str | None, str | None]:
        requires_label = command.action in (
            PositionOverrideAction.ASSIGN_POSITION,
            PositionOverrideAction.CHANGE_POSITION,
        )
        if requires_label != bool((command.position_label_id or "").strip()):
            raise PositionOverrideInvalidActionError(
                "Action and position_label_id are inconsistent."
            )
        if not requires_label:
            return None, None
        label = self._label_repo.get_by_id(command.position_label_id or "")
        if label is None:
            raise PositionOverrideInvalidLabelError("Position label not found.")
        if label.client_id != client_id:
            logger.info(
                "event=position_override_cross_tenant_rejected result_id=%s",
                command.result_id,
            )
            raise PositionOverrideCrossTenantError("Position label not found.")
        if label.status is not ClientPositionLabelStatus.ACTIVE:
            logger.info(
                "event=position_override_invalid_label_rejected label_id=%s",
                label.id,
            )
            raise PositionOverrideLabelInvalidatedError("Position label is invalidated.")
        return label.id, label.name

    @staticmethod
    def _validated_reason(
        code: PositionOverrideReasonCode, text: str | None
    ) -> str | None:
        normalized = " ".join((text or "").strip().split()) or None
        if normalized and ("<" in normalized or ">" in normalized):
            raise PositionOverrideInvalidActionError("reason_text must not contain HTML.")
        if normalized and len(normalized) > 1000:
            raise PositionOverrideInvalidActionError("reason_text is too long.")
        if code is PositionOverrideReasonCode.OTHER and not normalized:
            raise PositionOverrideInvalidActionError(
                "reason_text is required when reason_code is OTHER."
            )
        return normalized


class ListPositionOverrideHistoryUseCase:
    def __init__(
        self,
        *,
        override_repo: ManualPositionOverrideRepository,
        reconciliation_repo: PositionReconciliationRepository,
        manager: ManagePositionOverrideUseCase,
    ) -> None:
        self._override_repo = override_repo
        self._reconciliation_repo = reconciliation_repo
        self._manager = manager

    def execute(
        self,
        *,
        inventory_id: str,
        job_id: str,
        result_id: str,
        principal: AccessPrincipal,
    ) -> tuple[
        EffectiveProductPositionView,
        list[ProductPositionAssignment],
        list[ManualProductPositionOverride],
    ]:
        require_position_override_capability(principal, CAP_AUDIT)
        probe = PositionOverrideCommand(
            inventory_id=inventory_id,
            job_id=job_id,
            result_id=result_id,
            action=PositionOverrideAction.REMOVE_POSITION,
            position_label_id=None,
            reason_code=PositionOverrideReasonCode.OPERATOR_VERIFICATION,
            reason_text=None,
            expected_effective_version=0,
            idempotency_key="history-scope-probe",
            principal=principal,
        )
        self._manager._validate_scope(probe)
        effective = self._manager._effective_reader.load_for_job(
            job_id, result_ids=[result_id]
        )[result_id]
        return (
            effective,
            list(
                self._reconciliation_repo.list_result_assignment_history(
                    job_id, result_id
                )
            ),
            self._override_repo.list_history(job_id, result_id),
        )
