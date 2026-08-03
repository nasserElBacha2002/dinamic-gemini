"""Create, change, remove, restore, and audit manual product-position overrides."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import uuid4

from src.application.dto.access_principal import AccessPrincipal
from src.application.ports.client_position_label_repository import ClientPositionLabelRepository
from src.application.ports.clock import Clock
from src.application.ports.manual_position_override_repository import (
    ManualPositionOverrideRepository,
)
from src.application.ports.position_reconciliation_repository import (
    PositionReconciliationRepository,
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
)
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
from src.application.services.position_overrides.position_override_scope import (
    PositionOverrideScopeResolver,
)
from src.domain.client_position_label.entities import ClientPositionLabelStatus
from src.domain.position_overrides.entities import (
    EffectiveProductPositionView,
    ManualProductPositionOverride,
    PositionOverrideAction,
    PositionOverrideReasonCode,
)
from src.domain.position_reconciliation.entities import ProductPositionAssignment
from src.infrastructure.adapters.clock import UtcClock

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
    current_effective: EffectiveProductPositionView


class ManagePositionOverrideUseCase:
    def __init__(
        self,
        *,
        label_repo: ClientPositionLabelRepository,
        override_repo: ManualPositionOverrideRepository,
        effective_reader: EffectivePositionReader,
        scope_resolver: PositionOverrideScopeResolver,
        writes_enabled: bool,
        clock: Clock | None = None,
    ) -> None:
        self._label_repo = label_repo
        self._override_repo = override_repo
        self._effective_reader = effective_reader
        self._scope_resolver = scope_resolver
        self._writes_enabled = writes_enabled
        self._clock = clock or UtcClock()

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
        scope = self._scope_resolver.resolve(
            inventory_id=command.inventory_id,
            job_id=command.job_id,
            result_id=command.result_id,
            principal=command.principal,
        )
        client_id = scope.client_id
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
            current_effective = self._effective_reader.load_for_job(
                command.job_id, result_ids=[command.result_id]
            )[command.result_id]
            return PositionOverrideMutationResult(
                revision=replay,
                current_effective=current_effective,
            )

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
        now = self._clock.now()
        roles_snapshot = ",".join(sorted(command.principal.roles))[:64] or "unknown"
        revision = ManualProductPositionOverride(
            id=str(uuid4()),
            client_id=client_id,
            inventory_id=command.inventory_id,
            aisle_id=scope.aisle_id,
            job_id=command.job_id,
            result_id=command.result_id,
            source_asset_id=scope.source_asset_id or effective_before.source_asset_id,
            automatic_assignment_id=effective_before.automatic_assignment_id,
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
            created_by_role=roles_snapshot,
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
            expected_effective_version=command.expected_effective_version,
            expected_automatic_reconciliation_id=(
                effective_before.automatic_reconciliation_id
            ),
            expected_automatic_assignment_id=effective_before.automatic_assignment_id,
            expected_active_override_id=active.id if active else None,
            expected_active_override_version=active.version if active else None,
        )
        current_effective = self._effective_reader.load_for_job(
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
            "result_id=%s override_id=%s action=%s reason_code=%s actor_user_id=%s "
            "capability=%s",
            event,
            client_id,
            command.inventory_id,
            scope.aisle_id,
            command.job_id,
            command.result_id,
            saved.id,
            command.action.value,
            command.reason_code.value,
            command.principal.actor_id,
            capability,
        )
        return PositionOverrideMutationResult(
            revision=saved,
            current_effective=current_effective,
        )

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
        scope_resolver: PositionOverrideScopeResolver,
        effective_reader: EffectivePositionReader,
    ) -> None:
        self._override_repo = override_repo
        self._reconciliation_repo = reconciliation_repo
        self._scope_resolver = scope_resolver
        self._effective_reader = effective_reader

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
        self._scope_resolver.resolve(
            inventory_id=inventory_id,
            job_id=job_id,
            result_id=result_id,
            principal=principal,
        )
        effective = self._effective_reader.load_for_job(
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
