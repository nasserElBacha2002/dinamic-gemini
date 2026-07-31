"""Create / seal ordered capture sessions (Phase 1 positioning foundation)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import uuid4

from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import (
    OrderedCaptureSealRejectedError,
    OrderedCaptureSessionConflictError,
    OrderedCaptureSessionNotFoundError,
)
from src.application.ports.clock import Clock
from src.application.ports.ordered_capture_session_repository import (
    OrderedCaptureSessionRepository,
)
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    SourceAssetRepository,
)
from src.application.services.capture_sequence import validate_complete_sequence
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.domain.ordered_capture.entities import (
    OrderedCaptureSession,
    OrderedCaptureSessionStatus,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CreateOrderedCaptureSessionCommand:
    inventory_id: str
    aisle_id: str
    principal: AccessPrincipal
    created_by: str | None = None


@dataclass(frozen=True)
class SealOrderedCaptureSessionCommand:
    session_id: str
    expected_asset_count: int
    sequence_version: int
    principal: AccessPrincipal


class CreateOrderedCaptureSessionUseCase:
    def __init__(
        self,
        *,
        session_repo: OrderedCaptureSessionRepository,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        access_policy: InventoryAccessPolicy,
        clock: Clock,
    ) -> None:
        self._session_repo = session_repo
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._access_policy = access_policy
        self._clock = clock

    def execute(self, command: CreateOrderedCaptureSessionCommand) -> OrderedCaptureSession:
        self._access_policy.require_aisle(
            command.inventory_id, command.aisle_id, command.principal
        )
        inventory = self._inventory_repo.get_by_id(command.inventory_id)
        if inventory is None:
            raise OrderedCaptureSessionNotFoundError(command.inventory_id)
        now = self._clock.now()
        candidate = OrderedCaptureSession(
            id=str(uuid4()),
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            status=OrderedCaptureSessionStatus.OPEN,
            created_at=now,
            updated_at=now,
            client_id=getattr(inventory, "client_id", None),
            created_by=command.created_by or command.principal.actor_id,
        )
        session = self._session_repo.get_or_create_open_for_aisle(candidate)
        if session.id == candidate.id:
            logger.info(
                "capture_session_created capture_session_id=%s inventory_id=%s aisle_id=%s",
                session.id,
                session.inventory_id,
                session.aisle_id,
            )
        else:
            logger.info(
                "capture_session_created reuse_open session_id=%s aisle_id=%s",
                session.id,
                command.aisle_id,
            )
        return session


class GetOrderedCaptureSessionUseCase:
    def __init__(
        self,
        *,
        session_repo: OrderedCaptureSessionRepository,
        access_policy: InventoryAccessPolicy,
    ) -> None:
        self._session_repo = session_repo
        self._access_policy = access_policy

    def execute(self, session_id: str, *, principal: AccessPrincipal) -> OrderedCaptureSession:
        session = self._session_repo.get_by_id(session_id)
        if session is None:
            raise OrderedCaptureSessionNotFoundError(session_id)
        self._access_policy.require_aisle(session.inventory_id, session.aisle_id, principal)
        return session


class SealOrderedCaptureSessionUseCase:
    def __init__(
        self,
        *,
        session_repo: OrderedCaptureSessionRepository,
        asset_repo: SourceAssetRepository,
        access_policy: InventoryAccessPolicy,
        clock: Clock,
    ) -> None:
        self._session_repo = session_repo
        self._asset_repo = asset_repo
        self._access_policy = access_policy
        self._clock = clock

    def execute(self, command: SealOrderedCaptureSessionCommand) -> OrderedCaptureSession:
        session = self._session_repo.get_by_id(command.session_id)
        if session is None:
            raise OrderedCaptureSessionNotFoundError(command.session_id)
        self._access_policy.require_aisle(
            session.inventory_id, session.aisle_id, command.principal
        )
        logger.info(
            "capture_session_seal_requested capture_session_id=%s expected=%s version=%s",
            session.id,
            command.expected_asset_count,
            command.sequence_version,
        )
        if session.status == OrderedCaptureSessionStatus.SEALED:
            if (
                session.expected_asset_count == command.expected_asset_count
                and session.sequence_version == command.sequence_version
            ):
                logger.info(
                    "capture_session_sealed idempotent_hit capture_session_id=%s",
                    session.id,
                )
                return session
            raise OrderedCaptureSessionConflictError(
                "Session already sealed with incompatible expected_asset_count/sequence_version",
                code="CAPTURE_SESSION_SEAL_CONFLICT",
            )
        if session.status not in (
            OrderedCaptureSessionStatus.OPEN,
            OrderedCaptureSessionStatus.UPLOADING,
        ):
            raise OrderedCaptureSessionConflictError(
                f"Session status {session.status.value} cannot be sealed",
                code="CAPTURE_SESSION_INVALID_STATUS",
            )
        if command.sequence_version != session.sequence_version:
            raise OrderedCaptureSessionConflictError(
                "sequence_version mismatch",
                code="CAPTURE_SESSION_SEQUENCE_VERSION_MISMATCH",
            )
        assets = [
            a
            for a in self._asset_repo.list_by_aisle(session.aisle_id)
            if (a.ordered_capture_session_id or "") == session.id
        ]
        reasons = validate_complete_sequence(
            assets, expected_count=command.expected_asset_count
        )
        if reasons:
            logger.info(
                "capture_session_seal_rejected capture_session_id=%s reasons=%s",
                session.id,
                reasons,
            )
            raise OrderedCaptureSealRejectedError(
                "Seal rejected: incomplete or invalid sequence",
                reasons=reasons,
            )
        now = self._clock.now()
        session.status = OrderedCaptureSessionStatus.SEALED
        session.expected_asset_count = command.expected_asset_count
        session.uploaded_asset_count = len(assets)
        session.sealed_at = now
        session.updated_at = now
        self._session_repo.save(session)
        logger.info(
            "capture_session_sealed capture_session_id=%s expected=%s count=%s",
            session.id,
            session.expected_asset_count,
            session.uploaded_asset_count,
        )
        return session
