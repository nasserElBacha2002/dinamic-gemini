"""G4 — create a new aisle in the inventory and assign it to a temporal capture group."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from src.application.errors import (
    CaptureSessionGroupAlreadyAssignedError,
    CaptureSessionGroupNotFoundError,
    CaptureSessionNotFoundError,
)
from src.application.ports.capture_repositories import (
    CaptureSessionGroupRepository,
    CaptureSessionGroupSummary,
    CaptureSessionRepository,
)
from src.application.ports.clock import Clock
from src.application.services.capture_flow_observability import (
    LOG_OP_G4_ASSIGN_GROUP_CREATE_AISLE,
    RESULT_SUCCESS,
    emit_capture_flow_event,
    get_capture_flow_metrics,
)
from src.application.use_cases.aisles.create_aisle import CreateAisleCommand, CreateAisleUseCase
from src.application.use_cases.capture_sessions.get_capture_session_groups import (
    GetCaptureSessionGroupsUseCase,
)
from src.application.use_cases.shared.capture_session_group_assignment_guard import (
    ensure_group_aisle_assignment_allowed,
)
from src.domain.capture.entities import CaptureSessionGroupAisleAssignmentStatus

logger = logging.getLogger(__name__)


class CreateAisleAndAssignCaptureSessionGroupUseCase:
    def __init__(
        self,
        *,
        session_repo: CaptureSessionRepository,
        group_repo: CaptureSessionGroupRepository,
        create_aisle: CreateAisleUseCase,
        clock: Clock,
    ) -> None:
        self._session_repo = session_repo
        self._group_repo = group_repo
        self._create_aisle = create_aisle
        self._clock = clock
        self._list_groups = GetCaptureSessionGroupsUseCase(
            session_repo=session_repo, group_repo=group_repo
        )

    def execute(
        self,
        *,
        inventory_id: str,
        session_id: str,
        group_id: str,
        aisle_code: str,
        client_supplier_id: str | None = None,
    ) -> Sequence[CaptureSessionGroupSummary]:
        session = self._session_repo.get_by_id_for_inventory(session_id, inventory_id)
        if session is None:
            raise CaptureSessionNotFoundError(
                "Capture session not found for this inventory (session id does not match inventory scope)."
            )
        ensure_group_aisle_assignment_allowed(
            session, group_repo=self._group_repo, session_id=session_id
        )

        group = self._group_repo.get_by_id_and_session(group_id, session_id)
        if group is None:
            raise CaptureSessionGroupNotFoundError(
                "Capture session group not found for this session."
            )

        if group.assignment_status != CaptureSessionGroupAisleAssignmentStatus.UNASSIGNED:
            raise CaptureSessionGroupAlreadyAssignedError(
                "This capture session group is already assigned to an aisle."
            )

        aisle = self._create_aisle.execute(
            CreateAisleCommand(
                inventory_id=inventory_id,
                code=aisle_code,
                client_supplier_id=client_supplier_id,
            )
        )
        now = self._clock.now()
        group.assigned_aisle_id = aisle.id
        group.assignment_status = CaptureSessionGroupAisleAssignmentStatus.ASSIGNED_NEW
        group.assigned_at = now
        self._group_repo.update(group)

        out = self._list_groups.execute(inventory_id=inventory_id, session_id=session_id)
        get_capture_flow_metrics().record_g4_assign()
        emit_capture_flow_event(
            logger=logger,
            inventory_id=inventory_id,
            session_id=session_id,
            operation=LOG_OP_G4_ASSIGN_GROUP_CREATE_AISLE,
            result_status=RESULT_SUCCESS,
            group_id=group_id,
            aisle_id=aisle.id,
            counts={"groups_returned": len(out)},
        )
        return out
