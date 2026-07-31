"""CRUD + logical label emission for aisle locations (Phase 1)."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from uuid import uuid4

from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import (
    AisleLocationConflictError,
    AisleLocationLabelConflictError,
    AisleLocationLabelNotFoundError,
    AisleLocationNotFoundError,
    IdempotencyKeyReusedError,
)
from src.application.ports.aisle_location_repository import (
    AisleLocationLabelRepository,
    AisleLocationRepository,
)
from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, InventoryRepository
from src.application.services.image_processing.processing_action_idempotency_service import (
    hash_request_payload,
)
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.domain.aisle_location.entities import (
    AisleLocation,
    AisleLocationStatus,
    normalize_aisle_location_code,
)
from src.domain.aisle_location.label_entities import (
    POSITIONING_LABEL_PAYLOAD_VERSION,
    AisleLocationLabel,
    AisleLocationLabelStatus,
    PositioningLabelSignatureStatus,
)
from src.domain.aisle_location.payload import (
    build_positioning_label_payload,
    payload_sha256,
    validate_positioning_payload,
)

logger = logging.getLogger(__name__)

_ISSUE_LABEL_OP = "ISSUE_AISLE_LOCATION_LABEL"


@dataclass(frozen=True)
class CreateAisleLocationCommand:
    inventory_id: str
    aisle_id: str
    code: str
    principal: AccessPrincipal
    display_name: str | None = None
    description: str | None = None
    created_by: str | None = None


@dataclass(frozen=True)
class UpdateAisleLocationCommand:
    location_id: str
    inventory_id: str
    principal: AccessPrincipal
    display_name: str | None = None
    description: str | None = None
    status: AisleLocationStatus | None = None


@dataclass(frozen=True)
class IssueAisleLocationLabelCommand:
    location_id: str
    inventory_id: str
    principal: AccessPrincipal
    idempotency_key: str | None = None
    generated_by: str | None = None


@dataclass(frozen=True)
class InvalidateAisleLocationLabelCommand:
    label_id: str
    inventory_id: str
    principal: AccessPrincipal
    reason: str | None = None


class CreateAisleLocationUseCase:
    def __init__(
        self,
        *,
        location_repo: AisleLocationRepository,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        access_policy: InventoryAccessPolicy,
        clock: Clock,
    ) -> None:
        self._location_repo = location_repo
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._access_policy = access_policy
        self._clock = clock

    def execute(self, command: CreateAisleLocationCommand) -> AisleLocation:
        self._access_policy.require_aisle(
            command.inventory_id, command.aisle_id, command.principal
        )
        inventory = self._inventory_repo.get_by_id(command.inventory_id)
        if inventory is None or not inventory.client_id:
            raise AisleLocationConflictError(
                "Inventory must belong to a client to create aisle locations",
                code="AISLE_LOCATION_CLIENT_REQUIRED",
            )
        code = (command.code or "").strip()
        if not code:
            raise AisleLocationConflictError("code is required", code="AISLE_LOCATION_CODE_REQUIRED")
        normalized = normalize_aisle_location_code(code)
        existing = self._location_repo.get_active_by_normalized_code(
            client_id=inventory.client_id,
            aisle_id=command.aisle_id,
            normalized_code=normalized,
        )
        if existing is not None:
            raise AisleLocationConflictError(
                f"Active location with code {normalized} already exists",
                code="AISLE_LOCATION_CODE_CONFLICT",
            )
        now = self._clock.now()
        location = AisleLocation(
            id=str(uuid4()),
            client_id=inventory.client_id,
            aisle_id=command.aisle_id,
            code=code,
            normalized_code=normalized,
            status=AisleLocationStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            display_name=command.display_name,
            description=command.description,
            created_by=command.created_by or command.principal.actor_id,
        )
        self._location_repo.save(location)
        logger.info(
            "position_created position_id=%s aisle_id=%s code=%s",
            location.id,
            location.aisle_id,
            location.normalized_code,
        )
        return location


@dataclass(frozen=True)
class ListAisleLocationsCommand:
    inventory_id: str
    aisle_id: str
    principal: AccessPrincipal
    status: str | None = None
    search: str | None = None
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True)
class GetAisleLocationCommand:
    inventory_id: str
    location_id: str
    principal: AccessPrincipal


@dataclass(frozen=True)
class ListAisleLocationLabelsCommand:
    inventory_id: str
    location_id: str
    principal: AccessPrincipal
    status: str | None = None


class ListAisleLocationsUseCase:
    def __init__(
        self,
        *,
        location_repo: AisleLocationRepository,
        access_policy: InventoryAccessPolicy,
    ) -> None:
        self._location_repo = location_repo
        self._access_policy = access_policy

    def execute(self, command: ListAisleLocationsCommand) -> tuple[list[AisleLocation], int]:
        self._access_policy.require_aisle(
            command.inventory_id, command.aisle_id, command.principal
        )
        items = self._location_repo.list_by_aisle(
            command.aisle_id,
            status=command.status,
            search=command.search,
            limit=command.limit,
            offset=command.offset,
        )
        total = self._location_repo.count_by_aisle(
            command.aisle_id, status=command.status, search=command.search
        )
        return items, total


class GetAisleLocationUseCase:
    def __init__(
        self,
        *,
        location_repo: AisleLocationRepository,
        access_policy: InventoryAccessPolicy,
    ) -> None:
        self._location_repo = location_repo
        self._access_policy = access_policy

    def execute(self, command: GetAisleLocationCommand) -> AisleLocation:
        location = self._location_repo.get_by_id(command.location_id)
        if location is None:
            raise AisleLocationNotFoundError(command.location_id)
        self._access_policy.require_aisle(
            command.inventory_id, location.aisle_id, command.principal
        )
        return location


class ListAisleLocationLabelsUseCase:
    def __init__(
        self,
        *,
        location_repo: AisleLocationRepository,
        label_repo: AisleLocationLabelRepository,
        access_policy: InventoryAccessPolicy,
    ) -> None:
        self._location_repo = location_repo
        self._label_repo = label_repo
        self._access_policy = access_policy

    def execute(self, command: ListAisleLocationLabelsCommand) -> list[AisleLocationLabel]:
        location = self._location_repo.get_by_id(command.location_id)
        if location is None:
            raise AisleLocationNotFoundError(command.location_id)
        self._access_policy.require_aisle(
            command.inventory_id, location.aisle_id, command.principal
        )
        return list(
            self._label_repo.list_by_location(command.location_id, status=command.status)
        )


class UpdateAisleLocationUseCase:
    def __init__(
        self,
        *,
        location_repo: AisleLocationRepository,
        access_policy: InventoryAccessPolicy,
        clock: Clock,
    ) -> None:
        self._location_repo = location_repo
        self._access_policy = access_policy
        self._clock = clock

    def execute(self, command: UpdateAisleLocationCommand) -> AisleLocation:
        location = self._location_repo.get_by_id(command.location_id)
        if location is None:
            raise AisleLocationNotFoundError(command.location_id)
        self._access_policy.require_aisle(
            command.inventory_id, location.aisle_id, command.principal
        )
        if command.display_name is not None:
            location.display_name = command.display_name
        if command.description is not None:
            location.description = command.description
        if command.status is not None:
            location.status = command.status
        location.updated_at = self._clock.now()
        self._location_repo.save(location)
        return location


class IssueAisleLocationLabelUseCase:
    def __init__(
        self,
        *,
        location_repo: AisleLocationRepository,
        label_repo: AisleLocationLabelRepository,
        access_policy: InventoryAccessPolicy,
        clock: Clock,
    ) -> None:
        self._location_repo = location_repo
        self._label_repo = label_repo
        self._access_policy = access_policy
        self._clock = clock

    @staticmethod
    def _request_hash(*, client_id: str, location_id: str) -> str:
        return hash_request_payload(
            {
                "op": _ISSUE_LABEL_OP,
                "client_id": client_id,
                "location_id": location_id,
                "payload_version": POSITIONING_LABEL_PAYLOAD_VERSION,
            }
        )

    @staticmethod
    def _resolve_idempotent_label(
        existing: AisleLocationLabel,
        *,
        request_hash: str,
    ) -> AisleLocationLabel:
        if (existing.idempotency_request_hash or "") == request_hash:
            return existing
        raise IdempotencyKeyReusedError(
            "IDEMPOTENCY_KEY_REUSED: same key with a different issue-label fingerprint"
        )

    def execute(self, command: IssueAisleLocationLabelCommand) -> AisleLocationLabel:
        location = self._location_repo.get_by_id(command.location_id)
        if location is None:
            raise AisleLocationNotFoundError(command.location_id)
        self._access_policy.require_aisle(
            command.inventory_id, location.aisle_id, command.principal
        )
        if location.status != AisleLocationStatus.ACTIVE:
            raise AisleLocationConflictError(
                "Cannot issue label for inactive location",
                code="AISLE_LOCATION_INACTIVE",
            )
        idem_key = (command.idempotency_key or "").strip() or None
        request_hash: str | None = None
        if idem_key:
            request_hash = self._request_hash(
                client_id=location.client_id, location_id=location.id
            )
            existing = self._label_repo.get_by_client_idempotency_key(
                location.client_id, idem_key
            )
            if existing is not None:
                return self._resolve_idempotent_label(existing, request_hash=request_hash)
        public_identifier = f"pl_{secrets.token_urlsafe(12)}"
        label_id = str(uuid4())
        payload = build_positioning_label_payload(
            public_label_id=public_identifier,
            public_position_id=location.id,
            version=POSITIONING_LABEL_PAYLOAD_VERSION,
        )
        validate_positioning_payload(payload)
        now = self._clock.now()
        label = AisleLocationLabel(
            id=label_id,
            client_id=location.client_id,
            location_id=location.id,
            public_identifier=public_identifier,
            payload_version=POSITIONING_LABEL_PAYLOAD_VERSION,
            marker_version=1,
            template_version=1,
            status=AisleLocationLabelStatus.ACTIVE,
            payload=payload,
            generated_at=now,
            payload_hash=payload_sha256(payload),
            signature_status=PositioningLabelSignatureStatus.NOT_IMPLEMENTED,
            generated_by=command.generated_by or command.principal.actor_id,
            idempotency_key=idem_key,
            idempotency_request_hash=request_hash,
        )
        try:
            self._label_repo.save(label)
        except IdempotencyKeyReusedError:
            if not idem_key or not request_hash:
                raise
            raced = self._label_repo.get_by_client_idempotency_key(
                location.client_id, idem_key
            )
            if raced is None:
                raise
            return self._resolve_idempotent_label(raced, request_hash=request_hash)
        logger.info(
            "position_label_issued position_label_id=%s position_id=%s public_identifier=%s",
            label.id,
            location.id,
            label.public_identifier,
        )
        return label


class InvalidateAisleLocationLabelUseCase:
    def __init__(
        self,
        *,
        location_repo: AisleLocationRepository,
        label_repo: AisleLocationLabelRepository,
        access_policy: InventoryAccessPolicy,
        clock: Clock,
    ) -> None:
        self._location_repo = location_repo
        self._label_repo = label_repo
        self._access_policy = access_policy
        self._clock = clock

    def execute(self, command: InvalidateAisleLocationLabelCommand) -> AisleLocationLabel:
        label = self._label_repo.get_by_id(command.label_id)
        if label is None:
            raise AisleLocationLabelNotFoundError(command.label_id)
        location = self._location_repo.get_by_id(label.location_id)
        if location is None:
            raise AisleLocationNotFoundError(label.location_id)
        self._access_policy.require_aisle(
            command.inventory_id, location.aisle_id, command.principal
        )
        if label.status == AisleLocationLabelStatus.INVALIDATED:
            return label
        if label.status not in (
            AisleLocationLabelStatus.ACTIVE,
            AisleLocationLabelStatus.REPLACED,
        ):
            raise AisleLocationLabelConflictError(
                f"Cannot invalidate label in status {label.status.value}"
            )
        label.status = AisleLocationLabelStatus.INVALIDATED
        label.invalidated_at = self._clock.now()
        label.invalidation_reason = command.reason
        self._label_repo.save(label)
        logger.info(
            "position_label_invalidated position_label_id=%s position_id=%s",
            label.id,
            label.location_id,
        )
        return label
